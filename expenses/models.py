from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Expense(models.Model):
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
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.date} - {self.category} - {self.amount}"


