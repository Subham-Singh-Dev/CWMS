"""
leaves/services.py
Core business logic for leave assignment and cancellation.
Keeps views thin — all quota and attendance logic lives here.
"""
from datetime import timedelta
from django.db import transaction
from django.core.exceptions import ValidationError

from attendance.models import Attendance
from .models import LeaveAllocation, LeaveRecord, LeavePolicy


def get_or_create_allocation(employee, year):
    """
    Fetch existing allocation or create one from policy.
    Called every time a leave is assigned.
    """
    allocation, created = LeaveAllocation.objects.get_or_create(
        employee=employee,
        year=year,
        defaults=_get_default_days(employee)
    )
    return allocation


def _get_default_days(employee):
    """Get quota from LeavePolicy based on employee type."""
    try:
        emp_type = employee.employment_type.upper()
        # employee.employment_type must match LeavePolicy.employment_type
        policy = LeavePolicy.objects.get(
            employment_type=employee.employment_type
        )
        return {'total_days': policy.annual_leave_days}
    except LeavePolicy.DoesNotExist:
        # Fallback if no policy exists — default 15 days
        return {'total_days': 15}


def assign_leave(employee, leave_type, from_date, to_date,
                 total_days, reason, address_on_leave,
                 application_date, approved_by, department=''):
    """
    Main service — validates quota, creates LeaveRecord,
    updates LeaveAllocation, marks Attendance as 'L'.

    Raises ValidationError with user-friendly message on any failure.
    Wrapped in transaction.atomic() — all or nothing.
    """
    year = from_date.year

    with transaction.atomic():
        # 1. Get or create allocation
        allocation = get_or_create_allocation(employee, year)

        # 2. Check quota
        if total_days > allocation.remaining_days:
            raise ValidationError(
                f"{employee.name} only has {allocation.remaining_days} leave "
                f"days remaining in {year}. Cannot assign {total_days} days."
            )

        # 3. Check no salary already generated for these months
        from payroll.models import MonthlySalary
        from datetime import date

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

        # 4. Create LeaveRecord
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
            status='approved',
        )

        # 5. Update quota
        allocation.used_days += total_days
        allocation.save()

        # 6. Mark attendance as 'L' for each date in range
        current = from_date
        while current <= to_date:
            Attendance.objects.update_or_create(
                employee=employee,
                date=current,
                defaults={
                    'status': 'L',
                    'overtime_hours': 0,
                }
            )
            current += timedelta(days=1)

        return leave


def cancel_leave(leave_record, cancelled_by):
    """
    Cancel an approved leave:
    - Restores quota to LeaveAllocation
    - Reverts Attendance from 'L' back to 'A'
    - Marks LeaveRecord as cancelled

    Raises ValidationError if salary already paid for that period.
    """
    from payroll.models import MonthlySalary
    from datetime import date

    if leave_record.status == 'cancelled':
        raise ValidationError("This leave is already cancelled.")

    months_affected = set()
    current = leave_record.from_date
    while current <= leave_record.to_date:
        months_affected.add(date(current.year, current.month, 1))
        current += timedelta(days=1)

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

        # Revert attendance to Absent
        current = leave_record.from_date
        while current <= leave_record.to_date:
            Attendance.objects.filter(
                employee=leave_record.employee,
                date=current,
                status='L'
            ).update(status='A')
            current += timedelta(days=1)

        # Restore quota
        allocation = leave_record.allocation
        allocation.used_days -= leave_record.total_days
        allocation.save()

        # Mark cancelled
        leave_record.status = 'cancelled'
        leave_record.save()