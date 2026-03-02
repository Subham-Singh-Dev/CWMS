import csv
import secrets
import string
from decimal import Decimal
from datetime import datetime, date

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import transaction, IntegrityError, models
from django.db.models.functions import Cast, Substr
from django.core.exceptions import ValidationError

from employees.models import Employee, Role


class Command(BaseCommand):
    help = "Imports workers from CSV with strict validation and concurrency safety"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def generate_next_emp_id_locked(self):
        """
        Generate the next EMPxxxxx ID safely.
        MUST be called inside transaction.atomic().
        Uses row-level locking to prevent race conditions.
        """
        last_user = (
            User.objects
            .select_for_update()
            .filter(username__startswith="EMP")
            .annotate(
                num_part=Cast(Substr("username", 4), output_field=models.IntegerField())
            )
            .order_by("-num_part")
            .first()
        )

        next_num = (last_user.num_part if last_user else 0) + 1
        return f"EMP{next_num:05d}"

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs["csv_file"]

        # Ensure Worker group exists
        worker_group, _ = Group.objects.get_or_create(name="Worker")

        self.stdout.write(f"\n📂 Reading CSV file: {csv_file_path}\n")

        success_count = 0
        error_count = 0

        with open(csv_file_path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row_num, row in enumerate(reader, start=1):
                try:
                    with transaction.atomic():

                        # -------------------------
                        # A. Parse & Validate Data
                        # -------------------------
                        name = row["Name"].strip()
                        phone = row["Phone"].strip()
                        role_name = row["Role"].strip()

                        if not phone.isdigit() or len(phone) != 10:
                            raise ValidationError(
                                f"Invalid phone number '{phone}'. Must be 10 digits."
                            )

                        try:
                            wage = Decimal(row["Daily Wage"])
                            if wage <= 0:
                                raise ValidationError("Daily wage must be positive.")
                        except Exception:
                            raise ValidationError("Invalid daily wage format.")

                        try:
                            join_date = datetime.strptime(
                                row["Join Date"], "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            raise ValidationError(
                                "Invalid join date format. Use YYYY-MM-DD."
                            )

                        if join_date > date.today():
                            raise ValidationError(
                                f"Join date {join_date} cannot be in the future."
                            )

                        # -------------------------
                        # B. Role Handling
                        # -------------------------
                        role, created = Role.objects.get_or_create(
                            name=role_name,
                            defaults={"overtime_rate_per_hour": Decimal("0.00")},
                        )

                        if created:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"⚠️  Created role '{role_name}' with 0.00 OT rate."
                                )
                            )

                        # -------------------------
                        # C. Duplicate Prevention
                        # -------------------------
                        if Employee.objects.filter(phone_number=phone).exists():
                            self.stdout.write(
                                self.style.WARNING(
                                    f"⏭️  Row {row_num}: Skipped '{name}' "
                                    f"(phone {phone} already exists)"
                                )
                            )
                            continue

                        # -------------------------
                        # D. Generate EMP ID
                        # -------------------------
                        username = self.generate_next_emp_id_locked()

                        # -------------------------
                        # E. Password Generation
                        # -------------------------
                        alphabet = string.ascii_uppercase + string.digits
                        safe_alphabet = "".join(c for c in alphabet if c not in "IO")
                        password = "".join(
                            secrets.choice(safe_alphabet) for _ in range(10)
                        )

                        # -------------------------
                        # F. Create User
                        # -------------------------
                        user = User.objects.create_user(
                            username=username,
                            password=password,
                        )

                        # -------------------------
                        # G. Create Employee
                        # -------------------------
                        employee = Employee(
                            user=user,
                            name=name,
                            phone_number=phone,
                            role=role,
                            daily_wage=wage,
                            join_date=join_date,
                        )

                        employee.full_clean()
                        employee.save()

                        # -------------------------
                        # H. Group Assignment
                        # -------------------------
                        user.groups.add(worker_group)

                        # -------------------------
                        # I. Output Credentials
                        # -------------------------
                        self.stdout.write(
                            f"✅ Imported: {name} | ID: {username} | Password: {password}"
                        )

                        success_count += 1

                except ValidationError as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Row {row_num} Validation Error: {e}")
                    )
                    error_count += 1

                except IntegrityError as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"❌ Row {row_num} Database Integrity Error: {e}"
                        )
                    )
                    error_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Row {row_num} Critical Error: {e}")
                    )
                    error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 IMPORT COMPLETE\n"
                f"Success: {success_count}\n"
                f"Errors:  {error_count}\n"
            )
        )
