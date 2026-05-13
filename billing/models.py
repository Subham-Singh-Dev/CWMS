"""
Module: billing.models
App: billing
Purpose: Stores uploaded vendor/client bills and payment state for manager cashflow control.
Dependencies: Django file storage, timezone helpers.
Author note: Bill state is intentionally simple (paid/unpaid) to support fast dashboard summaries.
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal


class Bill(models.Model):
    """
    Single bill/invoice with optional PDF attachment and payment status.

    BUSINESS RULE: `paid_on` auto-syncs from `is_paid` in save() to keep state consistent.
    """
    BILL_TYPE_CLIENT = "client"
    BILL_TYPE_DEBTOR = "debtor"
    BILL_TYPE_CHOICES = [
        (BILL_TYPE_CLIENT, "Credit Customer"),
        (BILL_TYPE_DEBTOR, "Debtor"),
    ]

    bill_type = models.CharField(
        max_length=20,
        choices=BILL_TYPE_CHOICES,
        default=BILL_TYPE_DEBTOR,
        db_index=True,
        help_text="client = incoming money, debtor = outgoing money"
    )

    description = models.CharField(max_length=255)

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Amount paid so far"
    )

    pdf_file = models.FileField(
        upload_to="billing/billing_pdfs/",
        null=True,
        blank=True,
        help_text="Optional PDF file for the bill"
    )

    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    paid_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date when bill was paid"
    )

    @property
    def total_with_gst(self):
        """Calculate total amount including 18% GST dynamically."""
        gst_rate = Decimal("0.18")
        gst_amount = (self.amount * gst_rate).quantize(Decimal('0.01'))
        return self.amount + gst_amount

    # PROPERTY added for quick access to payment status in templates and logic without extra method calls
    @property
    def balance(self):
        """calculate remaining amount dynamically for display and logic without storing redundant data."""
        return max(Decimal("0.00"), self.total_with_gst - self.paid_amount)

    def __str__(self):
        """Return compact bill label for admin and logs."""
        return f"Bill #{self.id} - {self.description}"

    def save(self, *args, **kwargs):
        """
        Auto-calculate is_paid status based on partial payments.
        Synchronizes paid_on date from payment status before persisting.
        """
        # Ensure we don't accidentally get negative balances or None types
        if not self.paid_amount:
            self.paid_amount = Decimal("0.00")

        if not self.amount:
            self.amount = Decimal("0.00")
        
        # Business Logic: If paid amount matches or exceeds total amount, it's fully paid
        if self.paid_amount >= self.total_with_gst and self.total_with_gst > 0:
            self.is_paid = True
            if not self.paid_on:
                self.paid_on = timezone.now().date()
        else:
            self.is_paid = False
            self.paid_on = None  # Clear paid_on if not fully paid

        super().save(*args, **kwargs)



