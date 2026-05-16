"""
Module: king.models
App: king
Purpose: Owner-facing financial control entities (work orders, revenue, ledger) used by King dashboard.
Dependencies: Django auth User and Decimal-backed monetary fields.
Author note: Ledger and revenue entries are intentionally append-oriented for auditability.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import date




class WorkOrder(models.Model):
    """
    Contract/work-order master tracked through a lifecycle (pending->active->completed/cancelled).

    BUSINESS RULE: `wo_number` is auto-generated and immutable to keep external references stable.
    """
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
        """Default ordering by creation time for latest-first owner workflows."""
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """Assign sequential work-order number on first save and persist record."""
        # BUSINESS RULE: Human-friendly sequential WO number for contractor operations.
        if not self.wo_number:
            last = WorkOrder.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.wo_number = f"WO-{next_num:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        """Return short work-order label with number and project name."""
        return f"{self.wo_number} — {self.project_name}"

    def total_revenue_received(self):
        """Sum of all manual revenue entries linked to this work order."""
        return self.revenues.aggregate(
            t=models.Sum('amount')
        )['t'] or 0

    def balance_remaining(self):
        """Return remaining collectible amount after received revenues."""
        return self.order_value - self.total_revenue_received()


class Revenue(models.Model):
    """
    Manual revenue inflow entry optionally linked to a work order.

    BUSINESS RULE: work_order is nullable SET_NULL so revenue history survives if a work order
    is removed/archived.
    """
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
        """Newest revenue first to prioritize recent cashflow entries."""
        ordering = ['-date']

    def __str__(self):
        """Return concise revenue label with date, category, and amount."""
        return f"{self.date} — {self.get_category_display()} — ₹{self.amount}"

class LedgerAccount(models.Model):
    """
    Party / account master for the owner ledger.
 
    Each party the contractor transacts with gets one LedgerAccount record.
    LedgerEntry rows link to this — enabling party-wise account statements.
 
    BUSINESS RULE: name is unique so duplicate parties cannot be created accidentally.
    """
    name         = models.CharField(max_length=255, unique=True, verbose_name="Party Name")
    address      = models.TextField(blank=True, null=True, verbose_name="Address")
    gst_number   = models.CharField(max_length=15, blank=True, null=True, verbose_name="GST Number")
    phone        = models.CharField(max_length=15, blank=True, null=True, verbose_name="Phone")
    work_order   = models.ForeignKey(
        'WorkOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ledger_accounts',
        verbose_name="Linked Work Order"
    )
    created_by   = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE,
        verbose_name="Created By"
    )
    created_at   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['name']
        verbose_name        = "Ledger Account"
        verbose_name_plural = "Ledger Accounts"
 
    def __str__(self):
        return self.name
 
    def total_debit(self):
        """Sum of all debit entries linked to this account."""
        from django.db.models import Sum
        return self.ledger_entries.aggregate(t=Sum('debit'))['t'] or 0
 
    def total_credit(self):
        """Sum of all credit entries linked to this account."""
        from django.db.models import Sum
        return self.ledger_entries.aggregate(t=Sum('credit'))['t'] or 0
 
    def balance(self):
        """Net debit balance for this account."""
        from decimal import Decimal
        return Decimal(str(self.total_debit())) - Decimal(str(self.total_credit()))




class LedgerEntry(models.Model):
    """
    Double-sided ledger entry linked to a party account (LedgerAccount).
 
    FINANCIAL CRITICAL: Debit/Credit fields are Decimal and validated
    to block negative or zero-only entries.
 
    account is nullable SET_NULL — entries survive if a party account is deleted.
    """
    ENTRY_TYPE_CHOICES = [
        ('sale',    'Sale'),
        ('receipt', 'Receipt'),
        ('payment', 'Payment'),
        ('journal', 'Journal'),
    ]
 
    date           = models.DateField()
    value_date     = models.DateField(blank=True, null=True, verbose_name="Value Date")
    entry_type     = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES)
    voucher_number = models.CharField(max_length=50, blank=True, null=True,
                                      verbose_name="Ref No. / Cheque No.")
    particulars    = models.CharField(max_length=255, verbose_name="Particulars")
    branch_code    = models.CharField(max_length=20, blank=True, null=True,
                                      verbose_name="Branch Code")
    debit          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit         = models.DecimalField(max_digits=12, decimal_places=2, default=0)
 
    # Party account this entry belongs to
    account        = models.ForeignKey(
        LedgerAccount, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ledger_entries',
        verbose_name="Account / Party"
    )
 
    # Optional direct work-order link (independent of account's WO)
    work_order     = models.ForeignKey(
        'WorkOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ledger_entries',
        verbose_name="Linked Work Order"
    )
 
    created_by     = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    created_at     = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['date', 'created_at']
 
    @property
    def voucher_no(self):
        """Backward-compatible alias."""
        return self.voucher_number
 
    def clean(self):
        if self.debit < 0 or self.credit < 0:
            raise ValidationError("Debit/Credit cannot be negative.")
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("Either Debit or Credit must be greater than zero.")
 
    def _generate_voucher_number(self):
        code_map = {
            'sale':    'SAL',
            'receipt': 'RCPT',
            'payment': 'PAY',
            'journal': 'JRN',
        }
        prefix   = code_map.get(self.entry_type, 'LED')
        ref_date = self.date or timezone.localdate()
 
        if ref_date.month >= 4:
            fy_start, fy_end = ref_date.year, ref_date.year + 1
        else:
            fy_start, fy_end = ref_date.year - 1, ref_date.year
        fy_text = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}"
 
        fy_anchor      = date(fy_start, 4, 1)
        next_fy_anchor = date(fy_end,   4, 1)
        seq = LedgerEntry.objects.filter(
            entry_type=self.entry_type,
            date__gte=fy_anchor,
            date__lt=next_fy_anchor,
        ).count() + 1
 
        return f"{prefix}{seq:03d}/{fy_text}"
 
    def save(self, *args, **kwargs):
        if not self.voucher_number:
            self.voucher_number = self._generate_voucher_number()
        self.full_clean()
        super().save(*args, **kwargs)
 
    def __str__(self):
        party = self.account.name if self.account else 'Unassigned'
        return f"{self.date} | {self.entry_type} | {self.voucher_number} | {party} | Dr:{self.debit} Cr:{self.credit}"
