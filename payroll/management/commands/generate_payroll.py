from datetime import date
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError, PermissionDenied # Catch these new errors

from employees.models import Employee
from payroll.services import generate_monthly_salary, SalaryAlreadyGeneratedError


class Command(BaseCommand):
    help = "Generate payroll for all active employees for a given month"

    def add_arguments(self, parser):
        parser.add_argument("year", type=int, help="Year of payroll (e.g. 2026)")
        parser.add_argument("month", type=int, help="Month of payroll (1-12)")

    def handle(self, *args, **options):
        year = options["year"]
        month = options["month"]

        if not (1 <= month <= 12):
            self.stderr.write(self.style.ERROR("Month must be between 1 and 12"))
            return

        payroll_date = date(year, month, 1)

        self.stdout.write(
            self.style.SUCCESS(
                f"🚀 Starting payroll generation for {payroll_date.strftime('%B %Y')}"
            )
        )

        employees = Employee.objects.filter(is_active=True)

        if not employees.exists():
            self.stdout.write(self.style.WARNING("No active employees found."))
            return

        created = 0
        skipped = 0
        failed = 0

        from django.db import transaction

        with transaction.atomic():
            for employee in employees:
                try:
                    # --- PHASE 4: IMPROVED LOGGING ---
                    self.stdout.write(f"   Processing {employee.name}...", ending="\r") 

                    salary = generate_monthly_salary(employee, payroll_date)

                    # --- PHASE 4: HANDLE EMPTY RETURNS ---
                    if salary is None:
                        self.stdout.write(
                            self.style.WARNING(f"⚪ Skipped {employee.name}: No attendance & No debt")
                        )
                        skipped += 1
                        continue

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ {employee.name}: "
                            f"Net ₹{salary.net_pay} | "
                            f"Advance Deducted ₹{salary.advance_deducted}"
                        )
                    )
                    created += 1

                except SalaryAlreadyGeneratedError:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️  Skipped {employee.name}: Salary already exists")
                    )
                    skipped += 1
                
                # --- PHASE 4: CATCH SPECIFIC VALIDATION ERRORS ---
                except (PermissionDenied, ValidationError) as e:
                    self.stdout.write(
                        self.style.ERROR(f"🚫 Blocked {employee.name}: {e}")
                    )
                    failed += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Failed {employee.name}: {e}")
                    )
                    failed += 1

            self.stdout.write("-" * 40)
            self.stdout.write(self.style.SUCCESS(f"Created: {created}"))
            self.stdout.write(self.style.WARNING(f"Skipped: {skipped}"))
            self.stdout.write(self.style.ERROR(f"Failed:  {failed}"))
            self.stdout.write("-" * 40)