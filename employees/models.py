"""
Module: employees.models
App: employees
Purpose: Defines employee master data and role-level wage metadata that feed attendance and payroll.
Dependencies: Django auth User, payroll and attendance apps through foreign keys.
Author note: Statutory flags/rates are stored at employee level for auditable payroll snapshots.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
from django.contrib.auth.models import User  # <--- The Security Import
from decimal import Decimal


EMPLOYMENT_TYPE_CHOICES = [
    ('LOCAL', 'Local'),
    ('PERMANENT', 'Permanent'),
]

class Role(models.Model):
    """
    Represents a labor role (e.g., Mason, Helper) with shared overtime policy.

    BUSINESS RULE: Overtime rate is maintained at role level, not per employee,
    so payroll policy can be changed centrally without editing every worker record.
    """
    name = models.CharField(max_length=50, unique=True)
    overtime_rate_per_hour = models.DecimalField(max_digits=6, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        """Return role display name for admin and relation rendering."""
        return self.name

class Employee(models.Model):
    """
    Core worker profile used across attendance, payroll, and portal modules.

    SECURITY: The linked auth user is PROTECT to preserve payroll/audit history.
    BUSINESS RULE: daily_wage uses Decimal to guarantee paisa-level precision.
    EDGE CASE: Local employees cannot have PF/ESIC enabled.
    """
    # SECURITY: One employee must map to one login; PROTECT prevents orphaning
    # financial history if someone tries to delete the auth account.
    user = models.OneToOneField(User, on_delete=models.PROTECT)
    
    # --- IDENTITY ---
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    
    # Personal
    father_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # FINANCIAL CRITICAL: Decimal avoids float drift in wage math.
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    daily_wage = models.DecimalField(max_digits=8, decimal_places=2)
    employment_type = models.CharField(
        max_length=10,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default='LOCAL',
        help_text="Local = daily wage only. Permanent = subject to PF/ESIC deductions."
    )
    pf_applicable = models.BooleanField(
        default=False,
        help_text="If True, PF will be deducted during payroll generation."
    )
    esic_applicable = models.BooleanField(
        default=False,
        help_text="If True, ESIC will be deducted during payroll generation."
    )
    pf_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.1200'),
        help_text="Employee PF contribution rate. Default 12% = 0.1200"
    )
    esic_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.0075'),
        help_text="Employee ESIC contribution rate. Default 0.75% = 0.0075"
    )
    join_date = models.DateField()
    is_active = models.BooleanField(default=True)

    # Work
    working_location = models.CharField(max_length=100, blank=True, null=True)


    # Address
    current_address  = models.TextField(blank=True, null=True)
    permanent_address= models.TextField(blank=True, null=True)

    # Compliance (all optional — workers may not have these)
    aadhar_number    = models.CharField(max_length=12,  blank=True, null=True, unique=True)
    pan_number       = models.CharField(max_length=10,  blank=True, null=True, unique=True)
    uan_number       = models.CharField(max_length=12,  blank=True, null=True, unique=True)
    esic_number      = models.CharField(max_length=17,  blank=True, null=True, unique=True)
    bank_account_no  = models.CharField(max_length=20,  blank=True, null=True, unique=True)



    def clean(self):
        """Validate wage/date constraints and statutory applicability rules."""
        # Normalize optional compliance fields so blank strings are stored as None.
        optional_fields = [
            'aadhar_number',
            'pan_number',
            'uan_number',
            'esic_number',
            'bank_account_no',
            'phone_number',
        ]
        for field_name in optional_fields:
            value = getattr(self, field_name)
            if value is None:
                continue
            value = str(value).strip()
            setattr(self, field_name, value or None)

        if self.pan_number:
            self.pan_number = self.pan_number.upper()

        if self.daily_wage <= 0:
            raise ValidationError("Daily wage must be positive.")
        if self.join_date > timezone.now().date():
            raise ValidationError("Join date cannot be in the future.")
        if self.employment_type == 'LOCAL' and (self.pf_applicable or self.esic_applicable):
            raise ValidationError(
                "Local employees cannot have PF or ESIC applicable. Set both flags to False."
            )

        if self.aadhar_number and not self.aadhar_number.isdigit():
            raise ValidationError({"aadhar_number": "Aadhaar must contain digits only."})
        if self.aadhar_number and len(self.aadhar_number) != 12:
            raise ValidationError({"aadhar_number": "Aadhaar must be exactly 12 digits."})

        if self.uan_number and (not self.uan_number.isdigit() or len(self.uan_number) != 12):
            raise ValidationError({"uan_number": "UAN must be exactly 12 digits."})

        if self.esic_number and (not self.esic_number.isdigit() or len(self.esic_number) > 17):
            raise ValidationError({"esic_number": "ESIC number must be numeric and up to 17 digits."})

        if self.pan_number:
            pan_validator = RegexValidator(
                regex=r'^[A-Z]{5}[0-9]{4}[A-Z]$',
                message='PAN format must be like ABCDE1234F.'
            )
            pan_validator(self.pan_number)

    def clean_fields(self, exclude=None):
        """Normalize formatted identifier inputs before Django field validators run."""
        if self.aadhar_number:
            self.aadhar_number = str(self.aadhar_number).replace(' ', '').replace('-', '')
        if self.uan_number:
            self.uan_number = str(self.uan_number).replace(' ', '').replace('-', '')
        if self.esic_number:
            self.esic_number = str(self.esic_number).replace(' ', '').replace('-', '')
        if self.pan_number:
            self.pan_number = str(self.pan_number).replace(' ', '').upper()

        super().clean_fields(exclude=exclude)

    def __str__(self):
        """Return concise employee label with role context."""
        return f"{self.name} ({self.role.name})"
 