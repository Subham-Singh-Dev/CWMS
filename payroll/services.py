"""
payroll/services.py

The ONLY place where payroll financial logic lives.

STRICT ARCHITECTURAL RULE:
    Views, templates, admin, and management commands MUST NEVER:
    - Calculate wages, overtime, or deductions directly.
    - Create or modify Advance records outside of this file.
    - Read or write MonthlySalary financial fields directly.

    All money flows through this file. This ensures:
    - A single auditable source of truth for financial logic.
    - Consistent Decimal precision across all calculations.
    - Atomic database operations to prevent partial financial writes.

Public Functions:
    generate_monthly_salary(employee, month) -> MonthlySalary | None
    issue_advance(employee, amount, issued_date) -> Advance
"""



from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone  # <--- NEW IMPORT
from django.db.models import Sum, Count, Q

from payroll.models import MonthlySalary, Advance
from attendance.models import Attendance


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================

class SalaryAlreadyGeneratedError(Exception):
     """
    Raised when attempting to generate a salary that already exists.
    Callers (views/commands) should catch this and show a warning,
    not an error — duplicate generation is a common user mistake.
    """
     pass


def generate_monthly_salary(employee, month):
    """
    Generate and persist a salary record for ONE employee for ONE month.

    This function:
        1. Validates the employee and month (guards against bad input).
        2. Fetches attendance stats for the month.
        3. Calculates gross pay (present days + half days + paid leaves + overtime).
        4. Deducts outstanding advances using FIFO (oldest advance first).
        5. Persists an immutable salary snapshot to the database.

    Args:
        employee (Employee): The employee to generate salary for.
        month (date): Must be the first day of the target month (e.g. date(2025, 1, 1)).

    Returns:
        MonthlySalary: The generated salary record.
        None: If gross pay is 0 AND no advances are outstanding (nothing to record).

    Raises:
        ValueError: If month is not the first day of a month.
        ValidationError: If generating for a future month, or salary already paid.
        PermissionDenied: If employee is inactive or joined after the target month.
        SalaryAlreadyGeneratedError: If salary already exists for this employee/month.
    """
    # ── GUARD 1: Month must be the 1st ────────────────────────
    if month.day != 1:
        raise ValueError("Month must be the first day of the month")

    # ── GUARD 2: Prevent future payroll generation ─────────────
    # Cannot generate salary for a month that hasn't ended yet
    today = timezone.now().date()
    if month > today.replace(day=1):
        raise ValidationError(f"Cannot generate payroll for future month: {month.strftime('%B %Y')}")

    # ── GUARD 3: Employee join date check ──────────────────────
    # An employee cannot be paid for months before they joined
    if employee.join_date.replace(day=1) > month:
        raise PermissionDenied(f"Employee joined on {employee.join_date}, cannot generate salary for {month.strftime('%B %Y')}")

    # ── GUARD 4: Inactive employees cannot receive salary ──────
    if not employee.is_active:
        raise PermissionDenied("Inactive employee cannot receive salary")

    # ── GUARD 5: Prevent duplicate salary generation ───────────
    if MonthlySalary.objects.filter(employee=employee, month=month).exists():
        raise SalaryAlreadyGeneratedError(
            f"Salary already generated for {employee} - {month}"
        )
    
     # ── GUARD 6: Prevent modification of paid salary ───────────
    existing_salary = MonthlySalary.objects.filter(
        employee=employee, month=month).first()
    
    if existing_salary and existing_salary.is_paid:
        raise ValidationError(
            f"salary for {employee} - {month.strftime('%B %Y')} is already PAID and cannot be modified"
        )
    
    # ── STEP 1: Fetch attendance stats for the month ───────────
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

    # ── STEP 2: Paid leave logic ───────────────────────────────
    # Business Rule: First 2 absences per month are treated as paid leave
    paid_leaves = min(absent_days, 2)

    # ── STEP 3: Gross pay calculation ─────────────────────────
    daily_wage = employee.daily_wage
    half_day_multiplier = Decimal('0.5') 

    present_pay = present_days * daily_wage
    half_day_pay = half_days * (daily_wage * half_day_multiplier)
    paid_leave_pay = paid_leaves * daily_wage
    
    # SAFETY: Calculate overtime with NULL checks (prevents crash if role unmapped)
    # Logic unchanged: if employee has no role, overtime defaults to zero
    overtime_rate = employee.role.overtime_rate_per_hour if employee.role else Decimal('0.00')
    overtime_pay = overtime_hours * overtime_rate

    raw_gross_pay = (
        present_pay +
        half_day_pay +
        paid_leave_pay +
        overtime_pay
    )

    # Round to 2 decimal places using standard financial rounding
    gross_pay = raw_gross_pay.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 7. ADVANCE DEDUCTION (FIFO)
    remaining_salary = gross_pay
    total_advance_deducted = Decimal('0.00')

    # ── STEP 4: Skip zero-value records ───────────────────────
    # If employee earned nothing AND has no advances, skip record creation
    has_unsettled_advances = Advance.objects.filter(employee=employee, settled=False).exists()
    
    if gross_pay == 0 and not has_unsettled_advances:
        return None  # Caller receives None — no salary slip generated
    
     # ── STEP 5: FIFO Advance Deduction (inside atomic block) ───
    with transaction.atomic():

        # Hard guard: Re-check inside transaction to prevent race conditions
        if MonthlySalary.objects.filter(employee=employee, month=month).exists():
            raise ValidationError(
                "Advance deduction already processed for this employee and month."
            )
        
        # Lock advance rows to prevent concurrent modification
        unsettled_advances = Advance.objects.select_for_update().filter(
            employee=employee,
            settled=False
        ).order_by('issued_date')   # FIFO: oldest advance deducted first

        # Deduct from each advance until salary is exhausted or advances are cleared
        for advance in unsettled_advances:
            if remaining_salary <= 0:
                break 
            
            deduction = min(remaining_salary, advance.remaining_amount)
            
            remaining_salary -= deduction
            total_advance_deducted += deduction
            
            advance.remaining_amount -= deduction
            advance.remaining_amount = advance.remaining_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # Mark advance as fully settled if balance reaches zero
            if advance.remaining_amount == 0:
                advance.settled = True
            
            advance.save()

        # Calculate total remaining advance debt after this payroll
        remaining_advance = Advance.objects.filter(
            employee=employee,
            settled=False
        ).aggregate(total=Sum('remaining_amount'))['total'] or Decimal('0.00')

        # ── STEP 6: Persist immutable salary snapshot ──────────
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

#============================================================
# FUNCTION: issue_advance
# ============================================================




def issue_advance(employee, amount, issued_date):
    """
        Issue a cash advance (loan) to an employee.
    
        IMPORTANT — What this function does NOT do:
            - It does NOT deduct anything from salary.
            - FIFO deduction happens strictly inside generate_monthly_salary().
            - Views must NEVER create Advance objects directly.
    
        Args:
            employee (Employee): The employee receiving the advance.
            amount (Decimal | str): Advance amount (will be normalized to 2dp).
            issued_date (date): Date the advance was physically issued.
    
        Returns:
            Advance: The created advance record.
    
        Raises:
            ValidationError: If employee is inactive or amount is zero/negative.
        """

    # Business Rule: Inactive employees cannot receive advances
    if not employee.is_active:
        raise ValidationError("Cannot issue advance to inactive employee.")

     # Normalize to 2 decimal places for financial consistency
    amount = Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Defensive check: Reject zero or negative advance amounts
    if amount <= 0:
        raise ValidationError("Advance amount must be greater than zero.")

    # Atomic transaction ensures advance record is all-or-nothing
    with transaction.atomic():

        advance = Advance.objects.create(
            employee=employee,
            amount=amount,
            remaining_amount=amount,  # Initially full amount is unpaid
            issued_date=issued_date,
            settled=False
        )

    return advance