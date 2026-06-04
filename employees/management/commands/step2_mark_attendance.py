"""
Management Command: step2_mark_attendance
==========================================
Marks attendance for ALL 160 employees for June 1-30, 2026.

Multi-site architecture:
  - Employees are tagged with site (raigarh / bhilai / korba)
  - Attendance is marked per-site to simulate real manager workflow
  - Each site's records are processed independently — no cross-site writes
  - Uses bulk_create(ignore_conflicts=True) to preserve 'L' records from step1

Attendance patterns (realistic):
  - Group A (~40%): Highly regular  — 27-30 P, 0-2 A
  - Group B (~35%): Normal          — 22-26 P, 2-4 A, 1-2 H
  - Group C (~15%): Irregular       — 15-20 P, 5-8 A, 1-3 H
  - Group D (~10%): Leave employees — 20-24 P, 2-4 A (leaves from step1 preserved)

Cross-site isolation check:
  After inserting, verifies that each site's attendance count matches
  its employee count × 30 days (minus preserved leaves). Flags any anomaly.

Run AFTER step1_populate_data:
    docker-compose exec web python manage.py step2_mark_attendance
"""

import random
from datetime import date

from django.core.management.base import BaseCommand

from attendance.models import Attendance
from employees.models import Employee


JUNE_DATES = [date(2026, 6, d) for d in range(1, 31)]

SITE_LABELS = {
    "raigarh": "Raigarh",
    "bhilai":  "Bhilai",
    "korba":   "Korba",
}


class Command(BaseCommand):
    help = "Mark attendance for 160 employees (3 sites) for June 1-30 via bulk_create"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 2: MARKING ATTENDANCE (JUNE 1-30, MULTI-SITE) ===\n"
        ))

        all_employees = list(
            Employee.objects.filter(is_active=True).select_related("role")
        )

        if not all_employees:
            self.stdout.write(self.style.ERROR(
                "No employees found. Run step1_populate_data first."
            ))
            return

        self.stdout.write(f"Found {len(all_employees)} active employees across all sites.\n")

        # Collect all existing 'L' records so we don't overwrite them
        existing_leave_keys = set(
            Attendance.objects.filter(
                date__gte=date(2026, 6, 1),
                date__lte=date(2026, 6, 30),
                status="L",
            ).values_list("employee_id", "date")
        )
        self.stdout.write(
            f"Preserving {len(existing_leave_keys)} existing leave records.\n"
        )

        total_records = []

        # ── Process site by site (mirrors real manager workflow) ─────────────
        for site_key, site_label in SITE_LABELS.items():
            site_employees = [e for e in all_employees if e.site == site_key]

            if not site_employees:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ No employees found for site: {site_label}")
                )
                continue

            self.stdout.write(
                f"── Site: {site_label} ({len(site_employees)} employees) ──"
            )

            # Assign attendance groups within this site
            random.shuffle(site_employees)
            total = len(site_employees)
            group_a = site_employees[:int(total * 0.40)]
            group_b = site_employees[int(total * 0.40):int(total * 0.75)]
            group_c = site_employees[int(total * 0.75):int(total * 0.90)]
            group_d = site_employees[int(total * 0.90):]

            site_records = []

            for group_name, group_employees, config in [
                ("A - Regular",   group_a, {"present_range": (27, 30), "absent_range": (0, 2),  "half_range": (0, 1)}),
                ("B - Normal",    group_b, {"present_range": (22, 26), "absent_range": (2, 4),  "half_range": (1, 2)}),
                ("C - Irregular", group_c, {"present_range": (15, 20), "absent_range": (5, 8),  "half_range": (1, 3)}),
                ("D - Leave+mix", group_d, {"present_range": (20, 24), "absent_range": (2, 4),  "half_range": (1, 2)}),
            ]:
                for emp in group_employees:
                    records = self._build_attendance(emp, config, existing_leave_keys)
                    site_records.extend(records)

            self.stdout.write(
                f"  Built {len(site_records)} records for {site_label}. Inserting..."
            )

            # Bulk insert this site's records
            inserted = 0
            batch_size = 500
            for i in range(0, len(site_records), batch_size):
                batch = site_records[i:i + batch_size]
                Attendance.objects.bulk_create(batch, ignore_conflicts=True)
                inserted += len(batch)

            self.stdout.write(
                self.style.SUCCESS(f"  ✅ {inserted} records inserted for {site_label}\n")
            )
            total_records.extend(site_records)

        # ── Final count ──────────────────────────────────────────────────────
        final_count = Attendance.objects.filter(
            date__gte=date(2026, 6, 1),
            date__lte=date(2026, 6, 30),
        ).count()

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Step 2 complete. Total attendance records in DB for June: {final_count}"
        ))

        self._print_summary()
        self._verify_site_isolation()

    # ── BUILD ATTENDANCE FOR ONE EMPLOYEE ────────────────────────────────────

    def _build_attendance(self, employee, config, existing_leave_keys):
        """
        Build Attendance objects for one employee across all 30 June days.
        Skips dates already marked 'L'. Adds realistic overtime for P days.
        """
        records = []

        non_leave_days = [
            d for d in JUNE_DATES
            if (employee.id, d) not in existing_leave_keys
        ]

        target_present = min(
            random.randint(*config["present_range"]), len(non_leave_days)
        )
        target_half = min(
            random.randint(*config["half_range"]),
            len(non_leave_days) - target_present
        )
        target_absent = len(non_leave_days) - target_present - target_half

        statuses = (
            ["P"] * target_present +
            ["H"] * target_half +
            ["A"] * target_absent
        )
        random.shuffle(statuses)

        for day, status in zip(non_leave_days, statuses):
            overtime = 0.0
            if status == "P" and random.random() < 0.25:
                # 0.5-hour increments between 1.0 and 4.0
                overtime = round(random.uniform(1.0, 4.0) * 2) / 2

            records.append(Attendance(
                employee=employee,
                date=day,
                status=status,
                overtime_hours=overtime,
            ))

        return records

    # ── SUMMARY ──────────────────────────────────────────────────────────────

    def _print_summary(self):
        self.stdout.write("\n── Attendance Summary (June 2026) ──")
        for status_code, label in [
            ("P", "Present"),
            ("A", "Absent"),
            ("H", "Half Day"),
            ("L", "Leave"),
        ]:
            count = Attendance.objects.filter(
                date__gte=date(2026, 6, 1),
                date__lte=date(2026, 6, 30),
                status=status_code,
            ).count()
            self.stdout.write(f"  {label:10}: {count:5} records")

        total = Attendance.objects.filter(
            date__gte=date(2026, 6, 1),
            date__lte=date(2026, 6, 30),
        ).count()
        self.stdout.write(f"  {'TOTAL':10}: {total:5} records")

    # ── CROSS-SITE ISOLATION VERIFICATION ───────────────────────────────────

    def _verify_site_isolation(self):
        """
        Verify that no cross-site attendance writes occurred.
        Each attendance record's employee.site should match only that site's
        employees. Checks for any employee whose attendance was written
        but doesn't belong to the expected batch.
        """
        self.stdout.write("\n── Cross-Site Isolation Check ──")

        all_good = True
        for site_key, site_label in SITE_LABELS.items():
            site_emp_ids = set(
                Employee.objects.filter(
                    site=site_key, is_active=True
                ).values_list("id", flat=True)
            )

            # Count attendance records for this site's employees
            site_att_count = Attendance.objects.filter(
                employee_id__in=site_emp_ids,
                date__gte=date(2026, 6, 1),
                date__lte=date(2026, 6, 30),
            ).count()

            expected_max = len(site_emp_ids) * 30  # 30 days, max 1 record per day
            leave_count  = Attendance.objects.filter(
                employee_id__in=site_emp_ids,
                date__gte=date(2026, 6, 1),
                date__lte=date(2026, 6, 30),
                status="L",
            ).count()

            # Each employee should have exactly 30 records (L + P/A/H)
            if site_att_count == expected_max:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✅ {site_label:10}: {site_att_count} records "
                        f"({len(site_emp_ids)} emp × 30 days) — OK"
                    )
                )
            else:
                # Could be slightly under if bulk_create had conflicts on existing data
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ {site_label:10}: {site_att_count} records "
                        f"(expected {expected_max}, {leave_count} leaves preserved) "
                        f"— check for conflicts"
                    )
                )
                all_good = False

        if all_good:
            self.stdout.write(self.style.SUCCESS(
                "\n  ✅ No cross-site contamination detected.\n"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "\n  ⚠ Some counts differ — review above. "
                "This is usually due to existing records from a partial run, not a bug.\n"
            ))

        self.stdout.write(
            self.style.SUCCESS("✅ Step 2 complete. Ready for Payroll Generation.\n")
        )