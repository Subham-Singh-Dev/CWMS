"""Leave service layer.

Module: leaves.services
App: leaves
Purpose: Centralizes leave allocation, assignment, and cancellation logic.
Key responsibilities: Enforce leave quota, prevent payroll conflicts, and
keep Attendance in sync with approved/cancelled leave records.
Dependencies: leaves.models.LeaveAllocation/LeaveRecord/LeavePolicy,
attendance.models.Attendance, payroll.models.MonthlySalary, Django transactions.
Author note: All state mutations are wrapped in atomic transactions to prevent
partial updates when a validation fails mid-flow.
"""

# ============================================================
# IMPORTS
# ============================================================
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from attendance.models import Attendance
from payroll.models import MonthlySalary

from .models import LeaveAllocation, LeavePolicy, LeaveRecord


# ============================================================
# ALLOCATION
# ============================================================


def get_or_create_allocation(employee, year):
    """Fetch or create yearly leave allocation for an employee.

    Args:
        employee (Employee): Employee whose allocation is needed.
        year (int): Year for which allocation applies.

    Returns:
        LeaveAllocation: Existing or newly created allocation record.

    Raises:
        ValidationError: Propagates from model validation if defaults are invalid.

    Business Rule:
        Leave allocation must exist before any assignment to enforce quotas.
    """
    allocation, created = LeaveAllocation.objects.get_or_create(
        employee=employee,
        year=year,
        defaults=_get_default_days(employee)
    )
    return allocation


def _get_default_days(employee):
    """Resolve default leave quota from policy for an employee.

    Args:
        employee (Employee): Employee whose policy determines quota.

    Returns:
        dict: Defaults for LeaveAllocation creation.

    Raises:
        None.

    Business Rule:
        If no policy exists, default to 15 days to avoid blocking HR ops.
    """
    try:
        # Reason: Ensure policy lookup matches the employee's stored type.
        policy = LeavePolicy.objects.get(
            employment_type=employee.employment_type
        )
        return {"total_days": policy.annual_leave_days}
    except LeavePolicy.DoesNotExist:
        # Reason: Keep leave assignment functional when policy is missing.
        return {"total_days": 15}


# ============================================================
# ASSIGNMENT
# ============================================================


def assign_leave(
    employee,
    leave_type,
    from_date,
    to_date,
    total_days,
    reason,
    address_on_leave,
    application_date,
    approved_by,
    department="",
):
    """Assign leave and synchronize allocation and attendance.

    Args:
        employee (Employee): Employee requesting leave.
        leave_type (str): Leave type code (e.g. SL, CL, RH).
        from_date (date): First day of leave.
        to_date (date): Last day of leave (inclusive).
        total_days (Decimal): Number of leave days being requested.
        reason (str): Leave reason.
        address_on_leave (str): Contact address during leave.
        application_date (date): Date of leave application.
        approved_by (User): Approver for the leave request.
        department (str): Department label or code.

    Returns:
        LeaveRecord: The created leave record in approved status.

    Raises:
        ValidationError: If quota is insufficient or payroll is already paid.

    Business Rule:
        Leave cannot be assigned for months where salary is already paid.
    """
    year = from_date.year

    # Reason: Ensure quota + attendance updates are applied atomically.
    with transaction.atomic():
        allocation = get_or_create_allocation(employee, year)

        if total_days > allocation.remaining_days:
            raise ValidationError(
                f"{employee.name} only has {allocation.remaining_days} leave "
                f"days remaining in {year}. Cannot assign {total_days} days."
            )

        # Reason: Payroll freeze prevents retroactive leave edits.
        months_affected = set()
        current = from_date
        while current <= to_date:
            months_affected.add(date(current.year, current.month, 1))
            current += timedelta(days=1)

        for month_start in months_affected:
            if MonthlySalary.objects.filter(
                employee=employee, month=month_start, is_paid=True
            ).exists():
                raise ValidationError(
                    f"Salary for {month_start.strftime('%B %Y')} is already "
                    f"paid. Cannot assign leave for that period."
                )

        leave = LeaveRecord.objects.create(
            employee=employee,
            leave_type=leave_type,
            from_date=from_date,
            to_date=to_date,
            total_days=total_days,
            reason=reason,
            address_on_leave=address_on_leave,
            application_date=application_date,
            approved_by=approved_by,
            allocation=allocation,
            department=department,
            status="approved",
        )

        allocation.used_days += total_days
        allocation.save()

        # Reason: Attendance is the source for payroll leave pay calculation.
        current = from_date
        while current <= to_date:
            Attendance.objects.update_or_create(
                employee=employee,
                date=current,
                defaults={
                    "status": "L",
                    "overtime_hours": 0,
                }
            )
            current += timedelta(days=1)

        return leave


# ============================================================
# CANCELLATION
# ============================================================


def cancel_leave(leave_record, cancelled_by):
    """Cancel an approved leave and reverse its effects.

    Args:
        leave_record (LeaveRecord): Leave record to cancel.
        cancelled_by (User): User performing the cancellation.

    Returns:
        None

    Raises:
        ValidationError: If leave is already cancelled or payroll is paid.

    Business Rule:
        Leave cannot be cancelled when payroll is already finalized.
    """
    if leave_record.status == "cancelled":
        raise ValidationError("This leave is already cancelled.")

    months_affected = set()
    current = leave_record.from_date
    while current <= leave_record.to_date:
        months_affected.add(date(current.year, current.month, 1))
        current += timedelta(days=1)

    # Reason: Prevent partial revert if payroll freeze check fails.
    with transaction.atomic():
        for month_start in months_affected:
            if MonthlySalary.objects.filter(
                employee=leave_record.employee,
                month=month_start,
                is_paid=True
            ).exists():
                raise ValidationError(
                    f"Cannot cancel leave — salary for "
                    f"{month_start.strftime('%B %Y')} is already paid."
                )

        # Reason: Revert only leave-marked attendance to avoid overwriting fixes.
        current = leave_record.from_date
        while current <= leave_record.to_date:
            Attendance.objects.filter(
                employee=leave_record.employee,
                date=current,
                status="L",
            ).update(status="A")
            current += timedelta(days=1)

        allocation = leave_record.allocation
        allocation.used_days -= leave_record.total_days
        allocation.save()

        leave_record.status = "cancelled"
        leave_record.save()