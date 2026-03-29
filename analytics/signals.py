from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from analytics.models import AuditLog
from analytics.request_context import get_current_user, get_client_ip
from analytics.services.audit_service import infer_user_role

from attendance.models import Attendance
from payroll.models import MonthlySalary, Advance
from expenses.models import Expense
from billing.models import Bill
from king.models import Revenue, WorkOrder


def _safe_username(user):
    return user.username if user and user.is_authenticated else 'SYSTEM'


def _create_log(activity, action, entity_type, entity_id, entity_name, details=''):
    user = get_current_user()
    AuditLog.objects.create(
        user=user,
        username=_safe_username(user),
        user_role=infer_user_role(user),
        activity=activity,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        details=details,
        ip_address=get_client_ip(),
        status='success',
    )


@receiver(post_save, sender=Attendance)
def log_attendance_save(sender, instance, created, **kwargs):
    status_map = {'P': 'mark_present', 'A': 'mark_absent', 'H': 'mark_halfday'}
    action = status_map.get(instance.status, 'update') if created else 'update'
    _create_log(
        activity='attendance',
        action=action,
        entity_type='Attendance',
        entity_id=instance.id,
        entity_name=f"{instance.employee.name} ({instance.date})",
        details=f"Status={instance.get_status_display()}, OT={instance.overtime_hours}",
    )


@receiver(post_save, sender=MonthlySalary)
def log_salary_save(sender, instance, created, **kwargs):
    action = 'generate' if created else ('mark_paid' if instance.is_paid else 'update')
    _create_log(
        activity='payroll',
        action=action,
        entity_type='MonthlySalary',
        entity_id=instance.id,
        entity_name=f"{instance.employee.name} - {instance.month.strftime('%b %Y')}",
        details=f"Net=₹{instance.net_pay}, Paid={instance.is_paid}",
    )


@receiver(post_save, sender=Advance)
def log_advance_save(sender, instance, created, **kwargs):
    _create_log(
        activity='payroll',
        action='issue' if created else 'update',
        entity_type='Advance',
        entity_id=instance.id,
        entity_name=f"Advance to {instance.employee.name}",
        details=f"Amount=₹{instance.amount}, Remaining=₹{instance.remaining_amount}",
    )


@receiver(post_save, sender=Expense)
def log_expense_save(sender, instance, created, **kwargs):
    _create_log(
        activity='expense',
        action='create' if created else 'update',
        entity_type='Expense',
        entity_id=instance.id,
        entity_name=f"{instance.get_category_display()} ({instance.date})",
        details=f"Amount=₹{instance.amount}",
    )


@receiver(post_delete, sender=Expense)
def log_expense_delete(sender, instance, **kwargs):
    _create_log(
        activity='expense',
        action='delete',
        entity_type='Expense',
        entity_id=instance.id or 0,
        entity_name=f"{instance.get_category_display()} ({instance.date})",
        details=f"Amount=₹{instance.amount}",
    )


@receiver(post_save, sender=Bill)
def log_bill_save(sender, instance, created, **kwargs):
    action = 'create' if created else ('mark_paid' if instance.is_paid else 'update')
    _create_log(
        activity='bill',
        action=action,
        entity_type='Bill',
        entity_id=instance.id,
        entity_name=f"Bill #{instance.id}",
        details=f"Amount=₹{instance.amount}, Paid={instance.is_paid}",
    )


@receiver(post_save, sender=Revenue)
def log_revenue_save(sender, instance, created, **kwargs):
    _create_log(
        activity='revenue',
        action='create' if created else 'update',
        entity_type='Revenue',
        entity_id=instance.id,
        entity_name=f"Revenue ({instance.date})",
        details=f"Amount=₹{instance.amount}",
    )


@receiver(post_save, sender=WorkOrder)
def log_workorder_save(sender, instance, created, **kwargs):
    _create_log(
        activity='workorder',
        action='create' if created else 'update',
        entity_type='WorkOrder',
        entity_id=instance.id,
        entity_name=f"WorkOrder #{instance.id}",
        details=f"Status={instance.status}",
    )
