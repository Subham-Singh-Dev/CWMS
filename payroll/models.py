from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from employees.models import Employee

# ==========================================
# 1. ADVANCE MODEL (Phase 2 Addition)
# ==========================================
class Advance(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="advances"
    )

    # Financial Safety: Prevent negative money
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)] 
    )
    
    remaining_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0.00)]
    )

    issued_date = models.DateField()
    settled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["issued_date"]

    def __str__(self):
        status = "Settled" if self.settled else "Active"
        return f"Advance ₹{self.amount} for {self.employee} ({status})"

    def clean(self):
        # Rule: You cannot owe more than the original advance
        if self.remaining_amount is not None and self.amount is not None:
            if self.remaining_amount > self.amount:
                raise ValidationError("Remaining amount cannot be greater than original amount.")
        
        # Rule: If remaining is 0, it must be marked settled
        if self.remaining_amount == 0 and not self.settled:
            self.settled = True
            
    def save(self, *args, **kwargs):
        # Auto-fill remaining_amount on creation if not provided
        if self._state.adding and self.remaining_amount is None:
            self.remaining_amount = self.amount
        
        self.full_clean() # Force validation before saving
        super().save(*args, **kwargs)


# ==========================================
# 2. MONTHLY SALARY MODEL (Phase 1 Existing)
# ==========================================
class MonthlySalary(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='monthly_salaries'
    )

    month = models.DateField(help_text="Use first day of the month")

    days_present = models.PositiveIntegerField(default=0)
    half_days = models.PositiveIntegerField(default=0) 
    paid_leaves = models.PositiveIntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    gross_pay = models.DecimalField(max_digits=10, decimal_places=2)
    advance_deducted = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    net_pay = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_advance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_paid = models.BooleanField(default=False)
    
    # ⬇️ FIX 1: ADDED MISSING FIELD
    paid_on = models.DateField(null=True, blank=True, help_text="Date when payment was made")
    
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Monthly Salary"
        verbose_name_plural = "Monthly Salaries"
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'month'],
                name='unique_salary_per_employee_per_month'
            )
        ]

    def clean(self):
        if self.month.day != 1:
            raise ValidationError("Month must be the first day of the month.")

    def __str__(self):
        return f"{self.employee.name} - {self.month.strftime('%B %Y')}"

    # ⬇️ FIX 2 & 3: Lowercase 'self' and Correct Indentation
    def save(self, *args, **kwargs):
        # if marked PAID but no date set, auto-set to TODAY
        if self.is_paid and not self.paid_on:
            self.paid_on = timezone.now().date()

        # CRITICAL FIX: This must be OUTSIDE the if block
        super().save(*args, **kwargs)