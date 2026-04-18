"""
Module: attendance.models
App: attendance
Purpose: Stores day-wise attendance inputs that become the primary source for payroll computation.
Dependencies: employees.models.Employee, timezone-aware validation rules.
Author note: Validation intentionally enforces current-month discipline to reduce retroactive manipulation.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from employees.models import Employee


class Attendance(models.Model):
    """
    Single attendance row for one employee on one date.

    BUSINESS RULE: Exactly one row per employee/day to prevent duplicate salary credits.
    BUSINESS RULE: Overtime is valid only when status is Present.
    """
    STATUS_CHOICES = [
        ('P', 'Present'),
        ('A', 'Absent'),
        ('H', 'Half Day'),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='attendances'
    )
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES)
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    marked_at = models.DateTimeField(auto_now_add=True)
        
    

    class Meta:
        """Model metadata enforcing uniqueness and default attendance ordering behavior."""
        constraints = [
            # BUSINESS RULE: This uniqueness is critical for payroll integrity.
            models.UniqueConstraint(
                fields=['employee', 'date'],
                name='unique_employee_attendance'
            )
        ]
        

    def clean(self):
        """Validate temporal and overtime rules before persisting attendance rows."""
        today = timezone.now().date()
        
        # BUSINESS RULE: Future attendance is blocked to prevent speculative wage entries.
        if self.date > today:
            raise ValidationError("❌ Attendance date cannot be in the future.")

        # BUSINESS RULE: Previous-month lock protects closed payroll periods.
        if self.date.year < today.year or (self.date.year == today.year and self.date.month < today.month):
            raise ValidationError("❌ Cannot mark attendance for previous months. Only current month is allowed.")

        # RULE 3: Overtime validation
        if self.overtime_hours < 0:
            raise ValidationError("Overtime hours cannot be negative.")

        # BUSINESS RULE: Overtime is payable only on Present status.
        if self.status != 'P' and self.overtime_hours > 0:
            raise ValidationError(
                "Overtime can be added only if employee is present."
            )

    def save(self, *args, **kwargs):
        """Run full validation before save to guarantee integrity at model boundary."""
        # Always validate before saving
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        """Return human-readable attendance row identifier."""
        return f"{self.employee.name} - {self.date}"

    




