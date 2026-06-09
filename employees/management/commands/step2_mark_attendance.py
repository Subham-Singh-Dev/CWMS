import random
from datetime import date, timedelta
import calendar

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import Attendance
from employees.models import Employee

# Dynamic date generation for the current month
def get_current_month_dates():
    now = timezone.now()
    year = now.year
    month = now.month
    days_in_month = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, days_in_month + 1)]

SITE_LABELS = {
    "raigarh": "Raigarh",
    "bhilai":  "Bhilai",
    "korba":   "Korba",
}

class Command(BaseCommand):
    help = "Mark attendance for current month via bulk_create"

    def handle(self, *args, **options):
        now = timezone.now()
        current_dates = get_current_month_dates()
        
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== STEP 2: MARKING ATTENDANCE ({now.strftime('%B %Y')}, MULTI-SITE) ===\n"
        ))

        all_employees = list(Employee.objects.filter(is_active=True).select_related("role"))

        if not all_employees:
            self.stdout.write(self.style.ERROR("No employees found. Run step1_populate_data first."))
            return

        # Preserve existing 'L' records (Dynamic range)
        existing_leave_keys = set(
            Attendance.objects.filter(
                date__gte=current_dates[0],
                date__lte=current_dates[-1],
                status="L",
            ).values_list("employee_id", "date")
        )

        total_records = []
        for site_key, site_label in SITE_LABELS.items():
            site_employees = [e for e in all_employees if e.site == site_key]
            if not site_employees: continue

            self.stdout.write(f"── Site: {site_label} ({len(site_employees)} employees) ──")
            random.shuffle(site_employees)
            
            # Divide into patterns
            total = len(site_employees)
            groups = [
                ("A - Regular", site_employees[:int(total * 0.40)], {"present_range": (27, 30), "absent_range": (0, 2), "half_range": (0, 1)}),
                ("B - Normal", site_employees[int(total * 0.40):int(total * 0.75)], {"present_range": (22, 26), "absent_range": (2, 4), "half_range": (1, 2)}),
                ("C - Irregular", site_employees[int(total * 0.75):int(total * 0.90)], {"present_range": (15, 20), "absent_range": (5, 8), "half_range": (1, 3)}),
                ("D - Leave+mix", site_employees[int(total * 0.90):], {"present_range": (20, 24), "absent_range": (2, 4), "half_range": (1, 2)}),
            ]

            site_records = []
            for _, group_employees, config in groups:
                for emp in group_employees:
                    # Pass the dynamic date list
                    records = self._build_attendance(emp, config, existing_leave_keys, current_dates)
                    site_records.extend(records)

            Attendance.objects.bulk_create(site_records, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS(f" ✅ {len(site_records)} records inserted for {site_label}\n"))

        self.stdout.write(self.style.SUCCESS("✅ Step 2 complete. Ready for Payroll."))

    def _build_attendance(self, employee, config, existing_leave_keys, date_list):
        records = []
        non_leave_days = [d for d in date_list if (employee.id, d) not in existing_leave_keys]
        
        # Calculate status counts dynamically based on actual days in month
        target_present = min(random.randint(*config["present_range"]), len(non_leave_days))
        target_half = min(random.randint(*config["half_range"]), len(non_leave_days) - target_present)
        target_absent = len(non_leave_days) - target_present - target_half

        statuses = ["P"] * target_present + ["H"] * target_half + ["A"] * target_absent
        random.shuffle(statuses)

        for day, status in zip(non_leave_days, statuses):
            overtime = round(random.uniform(1.0, 4.0) * 2) / 2 if status == "P" and random.random() < 0.25 else 0.0
            records.append(Attendance(employee=employee, date=day, status=status, overtime_hours=overtime))
        return records