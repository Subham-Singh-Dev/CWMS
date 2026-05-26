"""
Management Command: step3_generate_payroll
==========================================
Calls generate_monthly_salary(employee, month) for every active employee
for May 2026.

Multi-site update:
  - Processes employees grouped by site for cleaner output
  - Shows per-site success/skip/fail counts in summary
  - Total across all 160 employees reported at end

Tracks:
  - Success count
  - Already-generated (skipped) count
  - Failed count with reasons

Run AFTER step2_mark_attendance:
    docker-compose exec web python manage.py step3_generate_payroll
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError

from employees.models import Employee
from payroll.services import generate_monthly_salary


MAY_2026 = date(2026, 5, 1)

SITE_LABELS = {
    "raigarh": "Raigarh",
    "bhilai":  "Bhilai",
    "korba":   "Korba",
}


class Command(BaseCommand):
    help = "Generate May 2026 payroll for all 160 employees (3 sites)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 3: GENERATING PAYROLL (MAY 2026) ===\n"
        ))

        all_employees = list(
            Employee.objects.filter(is_active=True).select_related("role")
        )

        if not all_employees:
            self.stdout.write(self.style.ERROR(
                "No employees found. Run step1_populate_data first."
            ))
            return

        self.stdout.write(
            f"Generating payroll for {len(all_employees)} employees across 3 sites...\n"
        )

        # Global counters
        total_success = 0
        total_skipped = 0
        total_failed  = 0
        all_failed_details = []

        # ── Process per site for readable output ─────────────────────────────
        for site_key, site_label in SITE_LABELS.items():
            site_employees = [e for e in all_employees if e.site == site_key]

            if not site_employees:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ No employees found for site: {site_label}")
                )
                continue

            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"\n── Site: {site_label} ({len(site_employees)} employees) ──"
                )
            )

            site_success = 0
            site_skipped = 0
            site_failed  = 0
            failed_details = []

            for emp in site_employees:
                try:
                    salary = generate_monthly_salary(emp, MAY_2026)
                    site_success += 1
                    self.stdout.write(
                        f"  ✅ {emp.name:<30} | "
                        f"Gross: {str(salary.gross_pay):>10} | "
                        f"Adv Ded: {str(salary.advance_deducted):>8} | "
                        f"Net: {str(salary.net_pay):>10}"
                    )

                except ValidationError as e:
                    msg = str(e.message if hasattr(e, "message") else e)
                    if "already" in msg.lower():
                        site_skipped += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ⏭  {emp.name:<30} | SKIPPED: {msg}"
                            )
                        )
                    else:
                        site_failed += 1
                        failed_details.append((emp.name, msg))
                        self.stdout.write(
                            self.style.ERROR(
                                f"  ❌ {emp.name:<30} | FAILED: {msg}"
                            )
                        )

                except Exception as e:
                    site_failed += 1
                    failed_details.append((emp.name, str(e)))
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ❌ {emp.name:<30} | ERROR: {e}"
                        )
                    )

            # Per-site mini summary
            self.stdout.write(
                f"\n  {site_label} → "
                f"Generated: {site_success}  "
                f"Skipped: {site_skipped}  "
                f"Failed: {site_failed}"
            )

            if failed_details:
                for name, reason in failed_details:
                    self.stdout.write(
                        self.style.ERROR(f"    ✗ {name}: {reason}")
                    )

            total_success += site_success
            total_skipped += site_skipped
            total_failed  += site_failed
            all_failed_details.extend(failed_details)

        # ── Global summary ───────────────────────────────────────────────────
        self.stdout.write("\n" + "─" * 60)
        self.stdout.write(self.style.SUCCESS(
            f"  Generated : {total_success}"
        ))
        self.stdout.write(self.style.WARNING(
            f"  Skipped   : {total_skipped} (already generated)"
        ))

        if total_failed:
            self.stdout.write(self.style.ERROR(
                f"  Failed    : {total_failed}"
            ))
            self.stdout.write("\nFailed employees:")
            for name, reason in all_failed_details:
                self.stdout.write(self.style.ERROR(f"  - {name}: {reason}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"  Failed    : 0"
            ))

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Step 3 complete. Run step4_verify_payroll next.\n"
        ))