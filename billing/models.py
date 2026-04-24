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

    def __str__(self):
        """Return compact bill label for admin and logs."""
        return f"Bill #{self.id} - {self.description}"

    def save(self, *args, **kwargs):
        """Synchronize paid_on date from payment status before persisting."""
        if self.is_paid and not self.paid_on:
            self.paid_on = timezone.now().date()

        if not self.is_paid:
            self.paid_on = None

        super().save(*args, **kwargs)



