from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User  # <--- The Security Import

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    overtime_rate_per_hour = models.DecimalField(max_digits=6, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Employee(models.Model):
    # --- SECURITY LINK ---
    # One Employee = One User Account. PROTECT ensures we don't accidentally delete a user.
    user = models.OneToOneField(User, on_delete=models.PROTECT)
    
    # --- IDENTITY ---
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    
    # --- JOB DETAILS ---
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    daily_wage = models.DecimalField(max_digits=8, decimal_places=2)
    join_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def clean(self):
        if self.daily_wage <= 0:
            raise ValidationError("Daily wage must be positive.")
        if self.join_date > timezone.now().date():
            raise ValidationError("Join date cannot be in the future.")

    def __str__(self):
        return f"{self.name} ({self.role.name})"
 