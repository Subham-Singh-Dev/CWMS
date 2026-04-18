"""
Module: analytics.models
App: analytics
Purpose: Defines persistent audit trail entities used for compliance, forensics, and dashboard activity feeds.
Dependencies: Django auth User and indexed query patterns for reporting/export.
Author note: AuditLog is append-only by convention; updates should be avoided outside retention cleanup.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class AuditLog(models.Model):
    """
    Comprehensive audit trail for all system actions.
    Tracks what was done, who did it, when, and on what entity.
    """
    
    # Activity Categories
    ACTIVITY_CHOICES = [
        ('attendance', 'Attendance'),
        ('payroll', 'Payroll'),
        ('expense', 'Expense'),
        ('bill', 'Bill'),
        ('employee', 'Employee'),
        ('user', 'User'),
        ('workorder', 'Work Order'),
        ('revenue', 'Revenue'),
        ('system', 'System'),
    ]
    
    # Action Types
    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('mark_paid', 'Marked as Paid'),
        ('mark_present', 'Marked Present'),
        ('mark_absent', 'Marked Absent'),
        ('mark_halfday', 'Marked Half-day'),
        ('generate', 'Generated'),
        ('issue', 'Issued'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('export', 'Exported'),
        ('other', 'Other'),
    ]
    
    # ── User ──────────────────────────────────────────────
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    username = models.CharField(max_length=150, help_text="Username snapshot")
    user_role = models.CharField(
        max_length=50,
        help_text="King or Manager role at time of action",
        blank=True
    )
    
    # ── Activity Details ──────────────────────────────────
    activity = models.CharField(
        max_length=20,
        choices=ACTIVITY_CHOICES,
        db_index=True
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        db_index=True
    )
    
    # ── Entity Being Modified ─────────────────────────────
    entity_type = models.CharField(
        max_length=50,
        help_text="Employee, MonthlySalary, Attendance, etc.",
        db_index=True
    )
    entity_id = models.IntegerField(
        help_text="Primary key of affected entity",
        db_index=True
    )
    entity_name = models.CharField(
        max_length=255,
        help_text="Human-readable name of affected entity",
        blank=True
    )
    
    # ── Changes ───────────────────────────────────────────
    details = models.TextField(
        blank=True,
        help_text="JSON or text summary of what changed"
    )
    old_values = models.TextField(
        blank=True,
        help_text="Previous values (for updates)"
    )
    new_values = models.TextField(
        blank=True,
        help_text="New values set"
    )
    
    # ── Metadata ──────────────────────────────────────────
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of requester"
    )
    status = models.CharField(
        max_length=20,
        choices=[('success', 'Success'), ('error', 'Error')],
        default='success'
    )
    error_message = models.TextField(
        blank=True,
        help_text="If status is error, what went wrong"
    )
    
    class Meta:
        """Model options and indexes optimized for audit timeline queries."""
        ordering = ['-timestamp']
        indexes = [
            # Fast newest-first scans for dashboards and exports.
            models.Index(fields=['-timestamp']),
            # User timeline queries for investigations.
            models.Index(fields=['user', '-timestamp']),
            # Activity-specific trend and filter queries.
            models.Index(fields=['activity', '-timestamp']),
            # Entity drill-down (e.g., all logs for one salary/employee row).
            models.Index(fields=['entity_type', 'entity_id']),
        ]
    
    def __str__(self):
        """Return compact audit event descriptor for admin/debug displays."""
        return f"[{self.activity}] {self.action} - {self.entity_name} by {self.username} on {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def log_attendance(cls, user, employee_name, status, date, ip_address=None):
        """Log attendance marking"""
        return cls.objects.create(
            user=user,
            username=user.username if user else 'SYSTEM',
            user_role='King' if hasattr(user, 'king_profile') else 'Manager' if hasattr(user, 'manager_profile') else 'Unknown',
            activity='attendance',
            action=f'mark_{status.lower()}' if status in ['present', 'absent', 'halfday'] else 'mark_present',
            entity_type='Attendance',
            entity_id=0,
            entity_name=f"{employee_name} - {date}",
            details=f"Status: {status}",
            ip_address=ip_address,
            status='success'
        )
    
    @classmethod
    def log_payroll(cls, user, action, employee_name, month, amount, ip_address=None):
        """Log payroll actions"""
        return cls.objects.create(
            user=user,
            username=user.username if user else 'SYSTEM',
            user_role='King' if hasattr(user, 'king_profile') else 'Manager' if hasattr(user, 'manager_profile') else 'Unknown',
            activity='payroll',
            action=action,  # 'generate', 'mark_paid', 'issue'
            entity_type='MonthlySalary',
            entity_id=0,
            entity_name=f"{employee_name} - {month}",
            details=f"Amount: ₹{amount}",
            ip_address=ip_address,
            status='success'
        )
    
    @classmethod
    def log_expense(cls, user, action, category, amount, date, ip_address=None):
        """Log expense actions"""
        return cls.objects.create(
            user=user,
            username=user.username if user else 'SYSTEM',
            user_role='King' if hasattr(user, 'king_profile') else 'Manager' if hasattr(user, 'manager_profile') else 'Unknown',
            activity='expense',
            action=action,
            entity_type='Expense',
            entity_id=0,
            entity_name=f"{category} - {date}",
            details=f"Amount: ₹{amount}",
            ip_address=ip_address,
            status='success'
        )
    
    @classmethod
    def log_bill(cls, user, action, bill_name, amount, ip_address=None):
        """Log bill actions"""
        return cls.objects.create(
            user=user,
            username=user.username if user else 'SYSTEM',
            user_role='King' if hasattr(user, 'king_profile') else 'Manager' if hasattr(user, 'manager_profile') else 'Unknown',
            activity='bill',
            action=action,
            entity_type='Bill',
            entity_id=0,
            entity_name=bill_name,
            details=f"Amount: ₹{amount}",
            ip_address=ip_address,
            status='success'
        )
    
    @classmethod
    def log_user_action(cls, user, action, details, ip_address=None):
        """Log user login/logout/system actions"""
        return cls.objects.create(
            user=user,
            username=user.username if user else 'SYSTEM',
            user_role='King' if user and hasattr(user, 'king_profile') else 'Manager' if user and hasattr(user, 'manager_profile') else 'Unknown',
            activity='user',
            action=action,
            entity_type='User',
            entity_id=user.id if user else 0,
            entity_name=user.username if user else 'SYSTEM',
            details=details,
            ip_address=ip_address,
            status='success'
        )

