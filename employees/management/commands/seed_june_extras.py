"""
Management Command: seed_june_extras
====================================
Injects new advances and leaves into June so the June payroll demo
has rich, realistic deductions and paid leaves.
"""

import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from employees.models import Employee
from attendance.models import Attendance
from payroll.services import issue_advance
from leaves.services import assign_leave
from portal.models import ManagerProfile


class Command(BaseCommand):
    help = "Inject June advances and leaves into an existing database for a realistic demo"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== SEEDING JUNE EXTRAS (ADVANCES & LEAVES) ===\n"))
        
        employees = list(Employee.objects.filter(is_active=True))
        managers = {p.site: p.user for p in ManagerProfile.objects.select_related('user').all()}
        
        if not employees or not managers:
            self.stdout.write(self.style.ERROR("No employees or managers found. Run step1 first!"))
            return
        
        with transaction.atomic():
            # ── 1. Issue Fresh June Advances ──
            adv_targets = random.sample(employees, 35)
            adv_count = 0
            for emp in adv_targets:
                amount = Decimal(random.choice(["2000", "3000", "5000", "8000"]))
                try:
                    # Issue advance dated June 5th
                    issue_advance(emp, amount, date(2026, 6, 5))
                    adv_count += 1
                except Exception as e:
                    pass
                    
            self.stdout.write(self.style.SUCCESS(f"  ✅ Issued {adv_count} new advances for June."))

            # ── 2. Assign June Leaves ──
            leave_targets = random.sample(employees, 20)
            leave_count = 0
            
            for emp in leave_targets:
                # Fallback to any manager if site manager isn't found
                mgr = managers.get(emp.site, list(managers.values())[0])
                
                start_d = date(2026, 6, 10)
                end_d   = date(2026, 6, 12)
                
                # CRITICAL: We must delete the 'P' or 'A' records that step2 already 
                # created for June 10-12 so we don't trigger database conflicts!
                Attendance.objects.filter(
                    employee=emp, 
                    date__range=(start_d, end_d)
                ).delete()
                
                try:
                    assign_leave(
                        employee=emp,
                        leave_type=random.choice(["CL", "SL"]),
                        from_date=start_d,
                        to_date=end_d,
                        total_days=3,
                        reason="Demo Leave injected for June",
                        address_on_leave="Local Town",
                        application_date=date(2026, 6, 1),
                        approved_by=mgr,
                        department="Construction Site"
                    )
                    leave_count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  ⚠ Leave failed for {emp.name}: {e}"))

            self.stdout.write(self.style.SUCCESS(f"  ✅ Assigned {leave_count} new 3-day leave blocks for June."))

        self.stdout.write(self.style.SUCCESS("\n✅ June Extras complete! You are ready to generate June Payroll.\n"))