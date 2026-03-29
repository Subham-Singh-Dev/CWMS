from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator




class WorkOrder(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('active',    'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    wo_number     = models.CharField(max_length=20, unique=True, editable=False)
    client_name   = models.CharField(max_length=100)
    client_contact= models.CharField(max_length=15, blank=True, null=True)
    project_name  = models.CharField(max_length=200)
    location      = models.CharField(max_length=200)
    order_value   = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    start_date    = models.DateField()
    end_date      = models.DateField()
    status        = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    description   = models.TextField(blank=True, null=True)
    created_by    = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at    = models.DateTimeField(auto_now_add=True)

    gst_number = models.CharField(
        max_length=15, blank=True, null=True,
        verbose_name="GST Number"
    )

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Auto-generate WO-001 format on creation
        if not self.wo_number:
            last = WorkOrder.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.wo_number = f"WO-{next_num:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.wo_number} — {self.project_name}"

    def total_revenue_received(self):
        """Sum of all manual revenue entries linked to this work order."""
        return self.revenues.aggregate(
            t=models.Sum('amount')
        )['t'] or 0

    def balance_remaining(self):
        return self.order_value - self.total_revenue_received()


class Revenue(models.Model):
    CATEGORY_CHOICES = [
        ('contract', 'Contract Payment'),
        ('labour',   'Labour Supply'),
        ('material', 'Material Supply'),
        ('other',    'Other'),
    ]
    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('upi',  'UPI'),
        ('bank', 'Bank'),
    ]

    date         = models.DateField()
    amount       = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    source       = models.CharField(max_length=255)
    category     = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES)
    work_order   = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='revenues'
    )
    created_by   = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} — {self.get_category_display()} — ₹{self.amount}"


class LedgerEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('sale',    'Sale'),
        ('receipt', 'Receipt'),
        ('payment', 'Payment'),
        ('journal', 'Journal'),
    ]

    date         = models.DateField()
    entry_type   = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES)
    voucher_no   = models.CharField(max_length=50, blank=True, null=True)
    particulars  = models.CharField(max_length=255)
    debit        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by   = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']

    def __str__(self):
        return f"{self.date} | {self.entry_type} | Dr:{self.debit} Cr:{self.credit}"
