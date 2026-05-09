"""
Management Command: step3_generate_payroll
==========================================
Calls generate_monthly_salary(employee, month) for every active employee
for May 2026.

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


class Command(BaseCommand):
    help = "Generate May 2026 payroll for all 100 employees"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 3: GENERATING PAYROLL (MAY 2026) ===\n"
        ))

        employees = list(
            Employee.objects.filter(is_active=True).select_related("role")
        )

        if not employees:
            self.stdout.write(self.style.ERROR(
                "No employees found. Run step1_populate_data first."
            ))
            return

        self.stdout.write(f"Generating payroll for {len(employees)} employees...\n")

        success_count  = 0
        skipped_count  = 0
        failed_count   = 0
        failed_details = []

        for emp in employees:
            try:
                salary = generate_monthly_salary(emp, MAY_2026)
                success_count += 1
                self.stdout.write(
                    f"  ✅ {emp.name:<30} | "
                    f"Gross: {str(salary.gross_pay):>10} | "
                    f"Advance Deducted: {str(salary.advance_deducted):>8} | "
                    f"Net: {str(salary.net_pay):>10}"
                )

            except ValidationError as e:
                # Already generated or business rule violation
                msg = str(e.message if hasattr(e, 'message') else e)
                if "already" in msg.lower():
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"  ⏭  {emp.name:<30} | SKIPPED: {msg}")
                    )
                else:
                    failed_count += 1
                    failed_details.append((emp.name, msg))
                    self.stdout.write(
                        self.style.ERROR(f"  ❌ {emp.name:<30} | FAILED: {msg}")
                    )

            except Exception as e:
                failed_count += 1
                failed_details.append((emp.name, str(e)))
                self.stdout.write(
                    self.style.ERROR(f"  ❌ {emp.name:<30} | ERROR: {e}")
                )

        # ── Summary ─────────────────────────────────────────────────────────
        self.stdout.write("\n" + "─" * 60)
        self.stdout.write(self.style.SUCCESS(
            f"  Generated : {success_count}"
        ))
        self.stdout.write(self.style.WARNING(
            f"  Skipped   : {skipped_count} (already generated)"
        ))
        if failed_count:
            self.stdout.write(self.style.ERROR(
                f"  Failed    : {failed_count}"
            ))
            self.stdout.write("\nFailed employees:")
            for name, reason in failed_details:
                self.stdout.write(f"  - {name}: {reason}")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"  Failed    : 0"
            ))

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Step 3 complete. Run step4_verify_payroll next.\n"
        ))
