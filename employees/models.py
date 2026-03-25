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
    
    # Personal
    father_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # --- JOB DETAILS ---
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    daily_wage = models.DecimalField(max_digits=8, decimal_places=2)
    join_date = models.DateField()
    is_active = models.BooleanField(default=True)

    # Work
    working_location = models.CharField(max_length=100, blank=True, null=True)


    # Address
    current_address  = models.TextField(blank=True, null=True)
    permanent_address= models.TextField(blank=True, null=True)

    # Compliance (all optional — workers may not have these)
    aadhar_number    = models.CharField(max_length=12,  blank=True, null=True)
    pan_number       = models.CharField(max_length=10,  blank=True, null=True)
    uan_number       = models.CharField(max_length=12,  blank=True, null=True)
    esic_number      = models.CharField(max_length=17,  blank=True, null=True)
    bank_account_no  = models.CharField(max_length=20,  blank=True, null=True)



    def clean(self):
        if self.daily_wage <= 0:
            raise ValidationError("Daily wage must be positive.")
        if self.join_date > timezone.now().date():
            raise ValidationError("Join date cannot be in the future.")

    def __str__(self):
        return f"{self.name} ({self.role.name})"
 