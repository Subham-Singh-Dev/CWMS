"""
Seed expenses for PDF verification.

Run:
  python seed_expenses_pdf.py --date 2026-05-19 --clear-date
"""

import argparse
import os
from datetime import date
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model

from expenses.models import Expense


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create sample expenses for daily PDF verification."
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Target expense date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--clear-date",
        action="store_true",
        help="Delete existing expenses on the target date before seeding.",
    )
    parser.add_argument(
        "--user",
        help="Username to use as created_by. Defaults to 'manager' or first user.",
    )
    return parser.parse_args()


def get_owner(username=None):
    User = get_user_model()
    if username:
        user = User.objects.filter(username=username).first()
        if user:
            return user
        raise ValueError(f"User '{username}' not found.")

    manager = User.objects.filter(username="manager").first()
    if manager:
        return manager

    first_user = User.objects.first()
    if first_user:
        return first_user

    return User.objects.create_user(
        username="manager",
        email="manager@cwms.local",
        password="password123",
        first_name="Project",
        last_name="Manager",
    )


def build_seed_rows():
    categories = [key for key, _ in Expense.CATEGORY_CHOICES]
    payment_modes = [key for key, _ in Expense.PAYMENT_MODE_CHOICES]

    category_labels = {
        "food": "Food",
        "fuel": "Fuel",
        "travel": "Travel",
        "material": "Material",
        "misc": "Misc",
    }
    payment_labels = {
        "cash": "Cash",
        "upi": "UPI",
        "bank": "Bank Transfer",
    }

    rows = []
    seed_amount = Decimal("120.00")
    amount_step = Decimal("37.50")
    idx = 0

    for category in categories:
        for mode in payment_modes:
            label = category_labels.get(category, category.title())
            pay_label = payment_labels.get(mode, mode.title())
            amount = (seed_amount + (amount_step * idx)).quantize(Decimal("0.01"))
            rows.append(
                (
                    category,
                    mode,
                    f"{label} expense via {pay_label}",
                    amount,
                )
            )
            idx += 1

    # Extra rows to validate grouped counts in the PDF.
    rows.extend(
        [
            ("food", "cash", "Snacks for crew", Decimal("85.75")),
            ("travel", "bank", "Bus tickets for site visit", Decimal("460.00")),
            ("fuel", "upi", "Diesel top-up", Decimal("980.25")),
        ]
    )
    return rows


def main():
    args = parse_args()
    try:
        target_date = date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("Invalid --date format. Use YYYY-MM-DD.") from exc

    owner = get_owner(args.user)

    if args.clear_date:
        Expense.objects.filter(date=target_date).delete()

    rows = build_seed_rows()
    created = 0

    for category, payment_mode, description, amount in rows:
        Expense.objects.create(
            date=target_date,
            category=category,
            description=description,
            amount=amount,
            payment_mode=payment_mode,
            created_by=owner,
        )
        created += 1

    print(
        f"Seeded {created} expenses for {target_date} "
        f"as user '{owner.username}'."
    )


if __name__ == "__main__":
    main()
