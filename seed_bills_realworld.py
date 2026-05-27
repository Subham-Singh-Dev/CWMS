"""
Seed realistic bill data for billing module.

Creates 10 Credit Customer and 10 Debtor bills by default.

Run:
  python seed_bills_realworld.py
  python seed_bills_realworld.py --count 12 --seed 42
"""

import argparse
import os
import random
from datetime import date, timedelta
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from billing.models import Bill


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create realistic credit customer and debtor bills."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of bills per type (client/debtor). Default: 10",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=26,
        help="Random seed for reproducible data. Default: 26",
    )
    return parser.parse_args()


def _pick_payment_ratio(rng, ratios):
    """Pick a payment ratio based on weighted buckets."""
    roll = rng.random()
    acc = 0.0
    for threshold, value in ratios:
        acc += threshold
        if roll <= acc:
            return value
    return ratios[-1][1]


def _build_descriptions(prefix, count):
    vendors = [
        "Excel Infra",
        "Shree Cement",
        "Sai Logistics",
        "Om Engineering",
        "Rathi Steel",
        "Trident Transport",
        "Vishwakarma Tools",
        "Bhilai Power",
        "Radha Hardware",
        "Kedar Aggregates",
    ]
    items = [
        "Formwork supply",
        "MS pipe fittings",
        "Scaffolding rental",
        "Diesel delivery",
        "Sand & aggregate",
        "Electrical cabling",
        "Site safety gear",
        "Concrete admixture",
        "Transport charges",
        "Welding electrodes",
    ]

    rows = []
    for idx in range(count):
        vendor = vendors[idx % len(vendors)]
        item = items[idx % len(items)]
        rows.append(f"{prefix} - {vendor} - {item} INV-{4200 + idx}")
    return rows


def create_bills(bill_type, descriptions, rng):
    created = 0
    base_amounts = [
        Decimal("12000"), Decimal("18500"), Decimal("24250"),
        Decimal("31500"), Decimal("48750"), Decimal("55000"),
        Decimal("68000"), Decimal("72000"), Decimal("89500"),
        Decimal("104000"),
    ]

    if bill_type == Bill.BILL_TYPE_CLIENT:
        # More likely to be paid or partially paid.
        payment_ratios = [
            (0.5, "full"),
            (0.3, "partial"),
            (0.2, "unpaid"),
        ]
    else:
        # Debtor bills tend to linger longer.
        payment_ratios = [
            (0.3, "full"),
            (0.4, "partial"),
            (0.3, "unpaid"),
        ]

    for idx, description in enumerate(descriptions):
        amount = base_amounts[idx % len(base_amounts)]
        # Add small variability to mimic negotiation/rounding
        delta = Decimal(str(rng.randint(-750, 1250)))
        amount = max(Decimal("500.00"), amount + delta).quantize(Decimal("0.01"))

        bill = Bill(
            bill_type=bill_type,
            description=description,
            amount=amount,
        )

        payment_state = _pick_payment_ratio(rng, payment_ratios)
        total_with_gst = bill.total_with_gst

        if payment_state == "full":
            bill.paid_amount = total_with_gst
            bill.paid_on = date.today() - timedelta(days=rng.randint(0, 20))
        elif payment_state == "partial":
            ratio = Decimal(str(rng.uniform(0.2, 0.8)))
            bill.paid_amount = (total_with_gst * ratio).quantize(Decimal("0.01"))
        else:
            bill.paid_amount = Decimal("0.00")

        bill.save()
        created += 1

    return created


def main():
    args = parse_args()
    rng = random.Random(args.seed)

    client_desc = _build_descriptions("Credit Customer", args.count)
    debtor_desc = _build_descriptions("Debtor", args.count)

    client_created = create_bills(Bill.BILL_TYPE_CLIENT, client_desc, rng)
    debtor_created = create_bills(Bill.BILL_TYPE_DEBTOR, debtor_desc, rng)

    print(
        f"Created {client_created} credit customer bills and "
        f"{debtor_created} debtor bills."
    )


if __name__ == "__main__":
    main()
