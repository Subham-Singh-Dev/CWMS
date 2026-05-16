from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from king.models import LedgerAccount, LedgerEntry


def pick_creator():
    User = get_user_model()
    return (
        User.objects.filter(groups__name="King").order_by("id").first()
        or User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.order_by("id").first()
    )


with transaction.atomic():
    creator = pick_creator()
    if not creator:
        raise RuntimeError("No users found. Create at least one user first.")

    account = LedgerAccount.objects.filter(name__iexact="EXCEL INFRA").first()
    if not account:
        account = LedgerAccount.objects.create(
            name="EXCEL INFRA",
            address="MIDC Industrial Area, Pune",
            gst_number="27ABCDE1234F1Z5",
            phone="9876543210",
            created_by=creator,
        )

    # Use account creator when possible, else fallback
    created_by = account.created_by if account.created_by_id else creator

    base_date = timezone.localdate() - timedelta(days=45)

    txns = [
        {"d": 0,  "t": "sale",    "p": "Supply of shuttering material - Invoice INV-4012",               "dr": "185000.00", "cr": "0.00",    "vd": 0, "bc": "PUN001"},
        {"d": 3,  "t": "receipt", "p": "NEFT received against INV-4012 (Part Payment)",                  "dr": "0.00",      "cr": "75000.00", "vd": 0, "bc": "PUN001"},
        {"d": 6,  "t": "sale",    "p": "MS pipe supports and clamps - Invoice INV-4041",                 "dr": "92000.00",  "cr": "0.00",    "vd": 0, "bc": "PUN001"},
        {"d": 9,  "t": "payment", "p": "Freight reimbursement paid via bank transfer",                   "dr": "0.00",      "cr": "12000.00", "vd": 1, "bc": "PUN001"},
        {"d": 12, "t": "receipt", "p": "UPI receipt for urgent site delivery adjustment",                 "dr": "0.00",      "cr": "18000.00", "vd": 0, "bc": "PUN001"},
        {"d": 15, "t": "sale",    "p": "Additional formwork accessories - Invoice INV-4090",             "dr": "64000.00",  "cr": "0.00",    "vd": 0, "bc": "PUN001"},
        {"d": 19, "t": "journal", "p": "Debit note raised for damaged return material",                   "dr": "8500.00",   "cr": "0.00",    "vd": 0, "bc": "PUN001"},
        {"d": 23, "t": "receipt", "p": "RTGS received against INV-4041 and INV-4090",                    "dr": "0.00",      "cr": "95000.00", "vd": 0, "bc": "PUN001"},
        {"d": 27, "t": "payment", "p": "On-site loading & handling charges paid on behalf of party",     "dr": "0.00",      "cr": "6700.00",  "vd": 1, "bc": "PUN001"},
        {"d": 31, "t": "sale",    "p": "Scaffolding couplers supply - Invoice INV-4152",                 "dr": "118000.00", "cr": "0.00",    "vd": 0, "bc": "PUN001"},
        {"d": 36, "t": "receipt", "p": "Bank receipt against running account settlement",                 "dr": "0.00",      "cr": "110000.00","vd": 0, "bc": "PUN001"},
        {"d": 41, "t": "journal", "p": "Year-end round-off and account reconciliation entry",            "dr": "0.00",      "cr": "800.00",   "vd": 0, "bc": "PUN001"},
    ]

    created_entries = []
    for row in txns:
        entry = LedgerEntry.objects.create(
            date=base_date + timedelta(days=row["d"]),
            value_date=base_date + timedelta(days=row["d"] + row["vd"]),
            entry_type=row["t"],
            particulars=row["p"],
            branch_code=row["bc"],
            debit=Decimal(row["dr"]),
            credit=Decimal(row["cr"]),
            account=account,
            work_order=account.work_order,   # keeps linkage if account already has a work order
            created_by=created_by,
        )
        created_entries.append(entry)

    total_debit = sum(e.debit for e in created_entries)
    total_credit = sum(e.credit for e in created_entries)

print(
    f"Inserted {len(created_entries)} transactions for '{account.name}'. "
    f"Total Debit={total_debit}, Total Credit={total_credit}"
)