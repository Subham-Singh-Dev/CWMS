"""
Module: expenses.models
App: expenses
Purpose: Captures operational site expenses categorized by type and payment mode.
Dependencies: Django auth user model.
Author note: Records are immutable in practice after lock window enforced at view layer.
"""

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Expense(models.Model):
    """
    One expense transaction row entered by manager-side operations.

    BUSINESS RULE: Category and payment_mode choices are controlled vocabularies to preserve
    reporting consistency.
    """
    CATEGORY_CHOICES = [
        ("food", "Food"),
        ("fuel", "Fuel"),
        ("travel", "Travel"),
        ("material", "Material"),
        ("misc", "Misc"),
    ]

    PAYMENT_MODE_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("bank", "Bank"),
    ]

    date = models.DateField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES)
    # SECURITY/AUDIT: CASCADE is acceptable because app user deletion is rare and system retains
    # separate audit logs for critical operations.
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return quick textual representation of expense row for listings."""
        return f"{self.date} - {self.category} - {self.amount}"


