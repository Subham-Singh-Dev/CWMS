from django.db import models
from django.utils import timezone
from decimal import Decimal


class Bill(models.Model):
    description = models.CharField(max_length=255)

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    pdf_file = models.FileField(upload_to="billing/billing_pdfs/")

    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    paid_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date when bill was paid"
    )

    def __str__(self):
        return f"Bill #{self.id} - {self.description}"

    def save(self, *args, **kwargs):
        if self.is_paid and not self.paid_on:
            self.paid_on = timezone.now().date()

        if not self.is_paid:
            self.paid_on = None

        super().save(*args, **kwargs)


