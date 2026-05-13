"""Payroll financial services.

Module: payroll.services
App: payroll
Purpose: Centralizes payroll-side computation and persistence so salary generation,
advance recovery, and statutory deductions are deterministic and auditable.
Key responsibilities: Salary generation, advance issuance, statutory deductions,
and FIFO advance recovery under transaction safety.
Dependencies: payroll.models.MonthlySalary/Advance, attendance.models.Attendance,
and Django transactions.
Author note: Financial logic is intentionally isolated here to prevent divergence
between UI, admin, and command paths.

STRICT ARCHITECTURAL RULE:
    Views, templates, admin, and management commands MUST NEVER:
    - Calculate wages, overtime, or deductions directly.
    - Create or modify Advance records outside of this file.
    - Read or write MonthlySalary financial fields directly.

    All money flows through this file. This ensures:
    - A single auditable source of truth for financial logic.
    - Consistent Decimal precision across all calculations.
    - Atomic database operations to prevent partial financial writes.
"""

# ============================================================
# IMPORTS
# ============================================================
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from attendance.models import Attendance
from payroll.models import Advance, MonthlySalary


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================
class SalaryAlreadyGeneratedError(Exception):
    """Signal that a salary already exists for an employee and month.

    Business rule: Duplicate generation should be treated as a warning condition,
    not a system error, because it is commonly caused by user retry actions.
    Fields: None.
    Constraints: Raised only when a salary row already exists for the same key.
    """


# ============================================================
# DEDUCTION CALCULATORS
# ============================================================


def _calculate_pf(gross_pay: Decimal, rate: Decimal) -> Decimal:
    """Calculate PF contribution from gross pay.

    Args:
        gross_pay (Decimal): Gross monthly pay before deductions.
        rate (Decimal): PF rate applied to gross pay.

    Returns:
        Decimal: PF contribution rounded to two decimals.

    Raises:
        None.

    Business Rule:
        Statutory PF must be rounded using ROUND_HALF_UP and never via floats.
    """
    # Avoid float drift in financial calculations.
    return (gross_pay * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calculate_esic(gross_pay: Decimal, rate: Decimal) -> Decimal:
    """Calculate ESIC contribution from gross pay.

    Args:
        gross_pay (Decimal): Gross monthly pay before deductions.
        rate (Decimal): ESIC rate applied to gross pay.

    Returns:
        Decimal: ESIC contribution rounded to two decimals.

    Raises:
        None.

    Business Rule:
        Statutory ESIC must be rounded using ROUND_HALF_UP and never via floats.
    """
    # Avoid float drift in financial calculations.
    return (gross_pay * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_monthly_salary(employee, month):
    """Generate and persist a salary record for one employee and month.

    Args:
        employee (Employee): The employee to generate salary for.
        month (date): First day of the target month (e.g. date(2025, 1, 1)).

    Returns:
        MonthlySalary | None: The salary record, or None when there is nothing to
        record (zero gross pay and no unsettled advances).

    Raises:
        ValueError: If `month` is not the first day of a month.
        ValidationError: If generating for a future month or salary is already paid.
        PermissionDenied: If employee is inactive or joined after the target month.
        SalaryAlreadyGeneratedError: If a salary already exists for this month.

    Business Rule:
        Salary must be generated from attendance, deductions applied, and advances
        recovered FIFO with transaction-level consistency.
    """
    if month.day != 1:
        raise ValueError("Month must be the first day of the month")

    today = timezone.now().date()
    if month > today.replace(day=1):
        raise ValidationError(
            f"Cannot generate payroll for future month: {month.strftime('%B %Y')}"
        )

    if employee.join_date.replace(day=1) > month:
        raise PermissionDenied(
            "Employee joined on {join_date}, cannot generate salary for "
            "{month}".format(
                join_date=employee.join_date,
                month=month.strftime("%B %Y"),
            )
        )

    if not employee.is_active:
        raise PermissionDenied("Inactive employee cannot receive salary")

    if MonthlySalary.objects.filter(employee=employee, month=month).exists():
        raise SalaryAlreadyGeneratedError(
            f"Salary already generated for {employee} - {month}"
        )

    existing_salary = MonthlySalary.objects.filter(
        employee=employee, month=month
    ).first()

    if existing_salary and existing_salary.is_paid:
        raise ValidationError(
            "salary for {employee} - {month} is already PAID and cannot be modified"
            .format(employee=employee, month=month.strftime("%B %Y"))
        )

    stats = Attendance.objects.filter(
        employee=employee,
        date__year=month.year,
        date__month=month.month
    ).aggregate(
        present_count=Count('id', filter=Q(status='P')),
        half_day_count=Count('id', filter=Q(status='H')),
        absent_count=Count('id', filter=Q(status='A')),
        leave_count=Count('id', filter=Q(status='L')),
        total_overtime=Sum('overtime_hours')
    )

    present_days = stats['present_count']
    half_days = stats['half_day_count']
    # Business rule: Missing leave rows should not block payroll.
    days_on_leave = stats["leave_count"] or 0
    overtime_hours = stats['total_overtime'] or Decimal('0.00')

    # BUSINESS RULE: All absences ('A') are unpaid; only approved leave ('L') pays.
    paid_leave_days = days_on_leave

    daily_wage = employee.daily_wage
    half_day_multiplier = Decimal('0.5')

    present_pay = present_days * daily_wage
    half_day_pay = half_days * (daily_wage * half_day_multiplier)
    paid_leave_pay = paid_leave_days * daily_wage
    
    # Reason: Avoid blocking payroll for employees without a role assignment.
    overtime_rate = (
        employee.role.overtime_rate_per_hour if employee.role else Decimal("0.00")
    )
    overtime_pay = overtime_hours * overtime_rate

    raw_gross_pay = (
        present_pay +
        half_day_pay +
        paid_leave_pay +
        overtime_pay
    )

    # Business rule: Monetary values must be stored at two decimals.
    gross_pay = raw_gross_pay.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    pf_deduction = Decimal('0.00')
    pf_rate_used = Decimal('0.0000')
    if employee.pf_applicable:
        pf_rate_used = employee.pf_rate
        pf_deduction = _calculate_pf(gross_pay, pf_rate_used)

    esic_deduction = Decimal('0.00')
    esic_rate_used = Decimal('0.0000')
    if employee.esic_applicable:
        esic_rate_used = employee.esic_rate
        esic_deduction = _calculate_esic(gross_pay, esic_rate_used)


    # Business rule: Protect statutory deductions before advance recovery.
    remaining_salary = max(Decimal('0.00'), gross_pay - pf_deduction - esic_deduction)
    total_advance_deducted = Decimal('0.00')

    # If employee earned nothing AND has no advances, skip record creation.
    has_unsettled_advances = Advance.objects.filter(
        employee=employee, settled=False
    ).exists()

    if gross_pay == 0 and not has_unsettled_advances:
        return None
    
    # ─── TRANSACTION SAFETY ──────────────────────────────────────────────────────
    # FINANCIAL CRITICAL: Lock advances and keep deductions atomic to prevent
    # partial recovery when concurrent payroll generation occurs.
    # ─────────────────────────────────────────────────────────────────────────────
    with transaction.atomic():

        # Reason: Prevent duplicate payroll rows under concurrent requests.
        if MonthlySalary.objects.filter(employee=employee, month=month).exists():
            raise ValidationError(
                "Advance deduction already processed for this employee and month."
            )

        # Reason: Avoid double-deduction when multiple jobs run in parallel.
        unsettled_advances = Advance.objects.select_for_update().filter(
            employee=employee,
            settled=False
        ).order_by('issued_date')   # FIFO: oldest advance deducted first

        # ─── FIFO ADVANCE DEDUCTION ───────────────────────────────────────────────
        # BUSINESS RULE: Recover advances oldest-first to prevent indefinite debt
        # rollover on newer advances while older ones stay unpaid.
        # ─────────────────────────────────────────────────────────────────────────

        for advance in unsettled_advances:
            if remaining_salary <= 0:
                break

            deduction = min(remaining_salary, advance.remaining_amount)

            remaining_salary -= deduction
            total_advance_deducted += deduction

            advance.remaining_amount -= deduction
            # Avoid float drift in financial calculations.
            advance.remaining_amount = advance.remaining_amount.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            if advance.remaining_amount == 0:
                advance.settled = True

            advance.save()

        remaining_advance = Advance.objects.filter(
            employee=employee,
            settled=False
        ).aggregate(total=Sum('remaining_amount'))['total'] or Decimal('0.00')

        total_deductions = total_advance_deducted + pf_deduction + esic_deduction
        net_pay = gross_pay - total_deductions

        salary = MonthlySalary.objects.create(
            employee=employee,
            month=month,
            days_present=present_days,
            half_days=half_days,
            paid_leaves=paid_leave_days,
            overtime_hours=overtime_hours,

            gross_pay=gross_pay,
            advance_deducted=total_advance_deducted,
            pf_deduction=pf_deduction,
            pf_rate_snapshot=pf_rate_used,
            esic_deduction=esic_deduction,
            esic_rate_snapshot=esic_rate_used,
            total_deductions=total_deductions,
            net_pay=net_pay,
            remaining_advance=remaining_advance,

            is_paid=False,
        )

    return salary


# ============================================================
# ADVANCE ISSUANCE
# ============================================================
def issue_advance(employee, amount, issued_date):
    """Issue a cash advance to an employee.

    Args:
        employee (Employee): The employee receiving the advance.
        amount (Decimal | str): Advance amount (normalized to two decimals).
        issued_date (date): Date the advance was physically issued.

    Returns:
        Advance: The created advance record.

    Raises:
        ValidationError: If employee is inactive or amount is zero/negative.

    Business Rule:
        Salary deduction for advances must only occur in
        `generate_monthly_salary()` with FIFO recovery.
    """

    # Business rule: Inactive employees cannot receive advances.
    if not employee.is_active:
        raise ValidationError("Cannot issue advance to inactive employee.")

    # Business rule: Normalize to two decimals for financial consistency.
    amount = Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Reason: Prevents invalid advances from entering recovery queue.
    if amount <= 0:
        raise ValidationError("Advance amount must be greater than zero.")

    # Reason: Maintain atomicity if related writes are added later.
    with transaction.atomic():

        advance = Advance.objects.create(
            employee=employee,
            amount=amount,
            remaining_amount=amount,  # Initially full amount is unpaid
            issued_date=issued_date,
            settled=False
        )

    return advance