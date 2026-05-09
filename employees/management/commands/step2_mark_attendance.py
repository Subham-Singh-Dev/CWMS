"""
Management Command: step2_mark_attendance
==========================================
Marks attendance for ALL employees for May 1–30, 2026.

Strategy:
  - Uses Attendance.objects.bulk_create(ignore_conflicts=True)
    → Bypasses Attendance.save() → Bypasses clean() date locks
    → ignore_conflicts=True skips employees who already have 'L'
      attendance from leave records created in Step 1

Attendance patterns (realistic):
  - Group A (~40 emp): Highly regular — 27-30 P, 0-2 A
  - Group B (~35 emp): Normal        — 22-26 P, 2-4 A, 1-2 H
  - Group C (~15 emp): Irregular     — 15-20 P, 5-8 A, 1-3 H
  - Group D (~10 emp): Had leave     — handled by step1 for May 1-5,
                                        rest filled in here

Run AFTER step1_populate_data:
    docker-compose exec web python manage.py step2_mark_attendance
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from attendance.models import Attendance
from employees.models import Employee


# May 1–30 date range
MAY_DATES = [date(2026, 5, d) for d in range(1, 31)]


class Command(BaseCommand):
    help = "Mark attendance for all employees May 1-30 via bulk_create (bypasses date locks)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 2: MARKING ATTENDANCE (MAY 1-30) ===\n"
        ))

        employees = list(Employee.objects.filter(is_active=True).select_related("role"))

        if not employees:
            self.stdout.write(self.style.ERROR(
                "No employees found. Run step1_populate_data first."
            ))
            return

        self.stdout.write(f"Found {len(employees)} active employees.")

        # Find employees who already have leave records (from step1)
        # so we don't overwrite their 'L' attendance
        from attendance.models import Attendance as Att
        existing_leave_keys = set(
            Att.objects.filter(
                date__gte=date(2026, 5, 1),
                date__lte=date(2026, 5, 30),
                status="L",
            ).values_list("employee_id", "date")
        )
        self.stdout.write(
            f"Found {len(existing_leave_keys)} existing leave attendance records — will preserve."
        )

        # Assign employees to groups
        random.shuffle(employees)
        total = len(employees)
        group_a = employees[:int(total * 0.40)]
        group_b = employees[int(total * 0.40):int(total * 0.75)]
        group_c = employees[int(total * 0.75):int(total * 0.90)]
        group_d = employees[int(total * 0.90):]  # leave employees

        attendance_records = []

        for group_name, group_employees, config in [
            ("A - Regular",   group_a, {"present_range": (27, 30), "absent_range": (0, 2), "half_range": (0, 1)}),
            ("B - Normal",    group_b, {"present_range": (22, 26), "absent_range": (2, 4), "half_range": (1, 2)}),
            ("C - Irregular", group_c, {"present_range": (15, 20), "absent_range": (5, 8), "half_range": (1, 3)}),
            ("D - Leave+mix", group_d, {"present_range": (20, 24), "absent_range": (2, 4), "half_range": (1, 2)}),
        ]:
            self.stdout.write(f"\nProcessing Group {group_name} ({len(group_employees)} employees)...")

            for emp in group_employees:
                records = self._build_attendance(
                    emp, config, existing_leave_keys
                )
                attendance_records.extend(records)

        # Bulk create — bypasses save() and clean() entirely
        self.stdout.write(f"\nBulk inserting {len(attendance_records)} attendance records...")

        # Insert in batches of 500 to avoid memory issues
        batch_size = 500
        total_inserted = 0
        for i in range(0, len(attendance_records), batch_size):
            batch = attendance_records[i:i + batch_size]
            Attendance.objects.bulk_create(batch, ignore_conflicts=True)
            total_inserted += len(batch)
            self.stdout.write(f"  Inserted batch {i // batch_size + 1} ({total_inserted} records so far)")

        # Final count
        final_count = Attendance.objects.filter(
            date__gte=date(2026, 5, 1),
            date__lte=date(2026, 5, 30),
        ).count()

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Step 2 complete. Total attendance records in DB for May: {final_count}"
        ))

        # Print a summary
        self._print_summary()

    def _build_attendance(self, employee, config, existing_leave_keys):
        """
        Build attendance records for one employee for all 30 days.
        Skips dates already marked as 'L' by leave service.
        Adds realistic overtime for present days.
        """
        records = []

        # Determine how many present/absent/half days for this employee
        total_non_leave_days = sum(
            1 for d in MAY_DATES
            if (employee.id, d) not in existing_leave_keys
        )

        target_present = random.randint(*config["present_range"])
        target_half    = random.randint(*config["half_range"])
        # Remaining = absent

        # Cap to available days
        target_present = min(target_present, total_non_leave_days)
        target_half    = min(target_half, total_non_leave_days - target_present)

        # Build status pool for non-leave days
        statuses = (
            ["P"] * target_present +
            ["H"] * target_half +
            ["A"] * (total_non_leave_days - target_present - target_half)
        )
        random.shuffle(statuses)

        status_idx = 0
        for day in MAY_DATES:
            # Skip if already marked as L (leave)
            if (employee.id, day) in existing_leave_keys:
                continue

            status = statuses[status_idx] if status_idx < len(statuses) else "A"
            status_idx += 1

            # Realistic overtime — only for P status, only some days
            overtime = 0
            if status == "P" and random.random() < 0.25:  # 25% chance of OT
                # Overtime between 1.0 and 4.0 hours
                overtime = round(random.uniform(1.0, 4.0) * 2) / 2  # 0.5 increments

            records.append(Attendance(
                employee=employee,
                date=day,
                status=status,
                overtime_hours=overtime,
            ))

        return records

    def _print_summary(self):
        """Print attendance distribution summary."""
        from django.db.models import Count

        self.stdout.write("\n── Attendance Summary (May 2026) ──")

        for status_code, label in [("P", "Present"), ("A", "Absent"), ("H", "Half Day"), ("L", "Leave")]:
            count = Attendance.objects.filter(
                date__gte=date(2026, 5, 1),
                date__lte=date(2026, 5, 30),
                status=status_code,
            ).count()
            self.stdout.write(f"  {label:10}: {count:5} records")

        total = Attendance.objects.filter(
            date__gte=date(2026, 5, 1),
            date__lte=date(2026, 5, 30),
        ).count()
        self.stdout.write(f"  {'TOTAL':10}: {total:5} records")
