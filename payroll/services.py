"""
IMPORTANT NOTE:
All payroll and financial calculations MUST live in this file.
Views, commands, templates, and admin must NEVER calculate or modify money values.
"""



from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone  # <--- NEW IMPORT
from django.db.models import Sum, Count, Q

from payroll.models import MonthlySalary, Advance
from attendance.models import Attendance


class SalaryAlreadyGeneratedError(Exception):
    pass


def generate_monthly_salary(employee, month):
    """
    Generate salary for ONE employee for ONE month.
    Includes Phase 4: defensive checks and zero-value skipping.
    """
    
    # 1. Validate month (Standard Check)
    if month.day != 1:
        raise ValueError("Month must be the first day of the month")

    # --- PHASE 4 GUARD: PREVENT FUTURE PAYROLL ---
    # We cannot generate salary for a month that hasn't started/finished yet
    today = timezone.now().date()
    if month > today.replace(day=1):
        raise ValidationError(f"Cannot generate payroll for future month: {month.strftime('%B %Y')}")

    # --- PHASE 4 GUARD: CHECK JOIN DATE ---
    # If employee joins Feb 2026, they can't be paid for Jan 2026
    # We compare month-start dates to handle mid-month joiners correctly
    if employee.join_date.replace(day=1) > month:
        raise PermissionDenied(f"Employee joined on {employee.join_date}, cannot generate salary for {month.strftime('%B %Y')}")

    # 2. Validate employee
    if not employee.is_active:
        raise PermissionDenied("Inactive employee cannot receive salary")

    # 3. Prevent duplicate salary
    if MonthlySalary.objects.filter(employee=employee, month=month).exists():
        raise SalaryAlreadyGeneratedError(
            f"Salary already generated for {employee} - {month}"
        )
    existing_salary = MonthlySalary.objects.filter(
        employee=employee, month=month).first()
    
    if existing_salary and existing_salary.is_paid:
        raise ValidationError(
            f"salary for {employee} - {month.strftime('%B %Y')} is already PAID and cannot be modified"
        )
    # 4. Fetch attendance stats
    stats = Attendance.objects.filter(
        employee=employee,
        date__year=month.year,
        date__month=month.month
    ).aggregate(
        present_count=Count('id', filter=Q(status='P')),
        half_day_count=Count('id', filter=Q(status='H')),
        absent_count=Count('id', filter=Q(status='A')),
        total_overtime=Sum('overtime_hours')
    )

    present_days = stats['present_count']
    half_days = stats['half_day_count']
    absent_days = stats['absent_count']
    overtime_hours = stats['total_overtime'] or Decimal('0.00')

    # 5. Paid leave logic
    paid_leaves = min(absent_days, 2)

    # 6. Wage calculations
    daily_wage = employee.daily_wage
    half_day_multiplier = Decimal('0.5') 

    present_pay = present_days * daily_wage
    half_day_pay = half_days * (daily_wage * half_day_multiplier)
    paid_leave_pay = paid_leaves * daily_wage
    overtime_pay = overtime_hours * employee.role.overtime_rate_per_hour

    raw_gross_pay = (
        present_pay +
        half_day_pay +
        paid_leave_pay +
        overtime_pay
    )
    gross_pay = raw_gross_pay.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 7. ADVANCE DEDUCTION (FIFO)
    remaining_salary = gross_pay
    total_advance_deducted = Decimal('0.00')

    # --- PHASE 4 GUARD: SKIP USELESS ROWS ---
    # If they earned 0 AND owe 0, there is no point creating a salary slip.
    has_unsettled_advances = Advance.objects.filter(employee=employee, settled=False).exists()
    
    if gross_pay == 0 and not has_unsettled_advances:
        return None  # Signal to the command that we skipped this person

    with transaction.atomic():

        #HARD GUARD: prevent re-entry into advance deduction for same salary
        if MonthlySalary.objects.filter(employee=employee, month=month).exists():
            raise ValidationError(
                "Advance deduction already processed for this employee and month."
            )
        
        # A. Fetch & Lock Rows
        unsettled_advances = Advance.objects.select_for_update().filter(
            employee=employee,
            settled=False
        ).order_by('issued_date')

        # B. Modify Advances
        for advance in unsettled_advances:
            if remaining_salary <= 0:
                break 
            
            deduction = min(remaining_salary, advance.remaining_amount)
            
            remaining_salary -= deduction
            total_advance_deducted += deduction
            
            advance.remaining_amount -= deduction
            advance.remaining_amount = advance.remaining_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            if advance.remaining_amount == 0:
                advance.settled = True
            
            advance.save()

        # C. Calculate Total Remaining Debt
        remaining_advance = Advance.objects.filter(
            employee=employee,
            settled=False
        ).aggregate(total=Sum('remaining_amount'))['total'] or Decimal('0.00')

        # D. Persist Snapshot
        salary = MonthlySalary.objects.create(
            employee=employee,
            month=month,
            days_present=present_days,
            half_days=half_days,
            paid_leaves=paid_leaves,
            overtime_hours=overtime_hours,
            
            gross_pay=gross_pay,
            advance_deducted=total_advance_deducted,
            net_pay=remaining_salary,
            remaining_advance=remaining_advance,
            
            is_paid=False,
        )

    return salary




def issue_advance(employee, amount, issued_date):
    """
    DOMAIN RULE: Issue cash advance to employee.

    IMPORTANT:
    - This function ONLY creates an Advance record.
    - It does NOT deduct anything from salary.
    - FIFO deduction happens strictly inside generate_monthly_salary().
    - Views must NEVER create Advance directly.
    """

    # Business Rule: Inactive employees cannot receive advances
    if not employee.is_active:
        raise ValidationError("Cannot issue advance to inactive employee.")

    # Financial Safety: Normalize to 2 decimal places
    amount = Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Defensive Rule: No zero or negative advances
    if amount <= 0:
        raise ValidationError("Advance amount must be greater than zero.")

    # Atomic transaction ensures financial integrity
    with transaction.atomic():

        advance = Advance.objects.create(
            employee=employee,
            amount=amount,
            remaining_amount=amount,  # Initially full amount is unpaid
            issued_date=issued_date,
            settled=False
        )

    return advance