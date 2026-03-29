from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from employees.models import Employee


class Attendance(models.Model):
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
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date'],
                name='unique_employee_attendance'
            )
        ]

    def clean(self):
        today = timezone.now().date()
        
        # RULE 1: Cannot mark future dates
        if self.date > today:
            raise ValidationError("❌ Attendance date cannot be in the future.")

        # RULE 2: Cannot mark previous months (only current month allowed)
        if self.date.year < today.year or (self.date.year == today.year and self.date.month < today.month):
            raise ValidationError("❌ Cannot mark attendance for previous months. Only current month is allowed.")

        # RULE 3: Overtime validation
        if self.overtime_hours < 0:
            raise ValidationError("Overtime hours cannot be negative.")

        # RULE 4: Overtime only for present employees
        if self.status != 'P' and self.overtime_hours > 0:
            raise ValidationError(
                "Overtime can be added only if employee is present."
            )

    def save(self, *args, **kwargs):
        # Always validate before saving
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.name} - {self.date}"

    




