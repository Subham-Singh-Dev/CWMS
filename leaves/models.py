from django.db import models

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class LeavePolicy(models.Model):
    """
    Defines annual leave quota per employment type.
    Contractor can update quota here without code changes.
    """
    EMPLOYMENT_TYPE_CHOICES = [
        ('PERMANENT', 'Permanent'),
        ('LOCAL', 'Local'),
    ]
    employment_type   = models.CharField(
        max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, unique=True
    )
    annual_leave_days = models.PositiveIntegerField(
        help_text="Total leave days per calendar year"
    )
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Leave Policies"

    def __str__(self):
        return f"{self.employment_type} — {self.annual_leave_days} days/year"


class LeaveAllocation(models.Model):
    """
    Per-employee per-year quota tracker.
    Created automatically when first leave is assigned for that year.
    Resets every January 1st (new record created for new year).
    """
    employee   = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='leave_allocations'
    )
    year       = models.PositiveIntegerField()
    total_days = models.PositiveIntegerField()
    used_days  = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'year')
        ordering = ['-year']

    @property
    def remaining_days(self):
        return self.total_days - self.used_days

    def __str__(self):
        return (
            f"{self.employee.name} — {self.year} — "
            f"{self.remaining_days}/{self.total_days} days remaining"
        )


class LeaveRecord(models.Model):
    """
    Individual leave assignment matching the SIPL hardcopy form.
    One record = one leave application.
    """
    LEAVE_TYPE_CHOICES = [
        ('EL', 'Earned Leave'),
        ('CL', 'Casual Leave'),
        ('SL', 'Sick Leave'),
    ]
    STATUS_CHOICES = [
        ('approved',  'Approved'),
        ('cancelled', 'Cancelled'),
    ]

    # Core — matches hardcopy form
    sl_number        = models.CharField(
        max_length=20, unique=True, editable=False
    )
    application_date = models.DateField(default=timezone.now)
    employee         = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='leave_records'
    )
    department       = models.CharField(
        max_length=100, blank=True,
        help_text="Department or site name"
    )
    leave_type       = models.CharField(max_length=5, choices=LEAVE_TYPE_CHOICES)
    from_date        = models.DateField()
    to_date          = models.DateField()
    total_days       = models.PositiveIntegerField()
    reason           = models.TextField()
    address_on_leave = models.TextField(
        blank=True,
        help_text="Worker's address/contact during leave"
    )
    status           = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='approved'
    )

    # Approval
    approved_by      = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='approved_leaves'
    )
    allocation       = models.ForeignKey(
        LeaveAllocation,
        on_delete=models.PROTECT,
        related_name='leave_records'
    )

    # Audit
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-from_date']

    def clean(self):
        if self.from_date and self.to_date:
            if self.to_date < self.from_date:
                raise ValidationError("To date cannot be before From date.")
            if self.from_date.year != self.to_date.year:
                raise ValidationError(
                    "Leave cannot span across calendar years. "
                    "Submit two separate applications."
                )

    def save(self, *args, **kwargs):
        # Auto-generate SL number on first save
        if not self.sl_number:
            year = self.from_date.year if self.from_date else timezone.now().year
            last = LeaveRecord.objects.filter(
                sl_number__startswith=f"LV{year}"
            ).count()
            self.sl_number = f"LV{year}{str(last + 1).zfill(4)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.sl_number} — {self.employee.name} — "
            f"{self.leave_type} — {self.from_date} to {self.to_date}"
        )