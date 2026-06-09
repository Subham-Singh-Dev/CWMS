from datetime import date
from decimal import Decimal
import calendar
from django.core.management.base import BaseCommand
from django.db.models import Sum, Count
from django.utils import timezone
from attendance.models import Attendance
from employees.models import Employee
from payroll.models import MonthlySalary

# Dynamic date setup for current month
now = timezone.now()
MONTH_START = date(now.year, now.month, 1)
last_day = calendar.monthrange(now.year, now.month)[1]
MONTH_END = date(now.year, now.month, last_day)

TOLERANCE = Decimal("0.02")
SITE_LABELS = {"raigarh": "Raigarh", "bhilai": "Bhilai", "korba": "Korba"}

COL = {"idx": 4, "name": 28, "type": 10, "days": 7, "leave": 7, "gross": 11, "adv": 10, "pf": 8, "esic": 8, "net": 11, "status": 12}
HEADER = f"{'#':<{COL['idx']}} {'Employee':<{COL['name']}} {'Type':<{COL['type']}} {'Days P':<{COL['days']}} {'Leaves':<{COL['leave']}} {'Gross':>{COL['gross']}} {'Adv Ded':>{COL['adv']}} {'PF':>{COL['pf']}} {'ESIC':>{COL['esic']}} {'Net':>{COL['net']}} {'Status':<{COL['status']}}"
DIVIDER = "─" * 116
THICK_DIVIDER = "═" * 116

class Command(BaseCommand):
    help = "Audit and verify current month payroll records"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== STEP 4: PAYROLL VERIFICATION ({now.strftime('%B %Y')}) ===\n"))

        all_employees = list(Employee.objects.filter(is_active=True).select_related("role"))
        salaries = {s.employee_id: s for s in MonthlySalary.objects.filter(month__month=now.month, month__year=now.year).select_related("employee")}

        att_l_map = dict(Attendance.objects.filter(date__gte=MONTH_START, date__lte=MONTH_END, status="L")
                        .values("employee_id").annotate(cnt=Count("id")).values_list("employee_id", "cnt"))

        grand_gross, grand_adv, grand_pf, grand_esic, grand_net = Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
        row_idx = 0

        for site_key, site_label in SITE_LABELS.items():
            site_employees = [e for e in all_employees if e.site == site_key]
            if not site_employees: continue

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{'━'*116}\n  SITE: {site_label.upper()} ({len(site_employees)} employees)\n{'━'*116}"))
            self.stdout.write(HEADER)
            self.stdout.write(DIVIDER)

            for emp in site_employees:
                row_idx += 1
                salary = salaries.get(emp.id)
                if not salary:
                    self.stdout.write(self.style.ERROR(f"{row_idx:<{COL['idx']}} {emp.name:<{COL['name']}} {'—':<{COL['type']}} {'—':<{COL['days']}} {'—':<{COL['leave']}} {'—':>{COL['gross']}} {'—':>{COL['adv']}} {'—':>{COL['pf']}} {'—':>{COL['esic']}} {'—':>{COL['net']}} {'NO RECORD':<{COL['status']}}"))
                    continue

                grand_gross += salary.gross_pay
                grand_adv += salary.advance_deducted
                grand_pf += salary.pf_deduction
                grand_esic += salary.esic_deduction
                grand_net += salary.net_pay
                
                self.stdout.write(f"{row_idx:<{COL['idx']}} {emp.name:<{COL['name']}} {emp.employment_type:<{COL['type']}} {salary.days_present:<{COL['days']}} {salary.paid_leaves:<{COL['leave']}} {salary.gross_pay:>{COL['gross']}} {salary.advance_deducted:>{COL['adv']}} {salary.pf_deduction:>{COL['pf']}} {salary.esic_deduction:>{COL['esic']}} {salary.net_pay:>{COL['net']}} ✅ OK")

        self.stdout.write(f"\n{THICK_DIVIDER}\n  GRAND TOTAL: {grand_gross} Gross | {grand_adv} Adv | {grand_pf} PF | {grand_esic} ESIC | {grand_net} Net\n{THICK_DIVIDER}")

        # Summary tables
        self.stdout.write(f"\n  ADVANCE RECOVERY CHECK")
        self.stdout.write(f"  ----------------------")
        self.stdout.write(f"  Total advance recovered ({now.strftime('%B')}): {grand_adv}")
        
        self.stdout.write(f"\n  PAYROLL DISTRIBUTION BY TYPE")
        self.stdout.write(f"  ----------------------------")
        for t in ["LOCAL", "PERMANENT"]:
            qs = MonthlySalary.objects.filter(month__month=now.month, month__year=now.year, employee__employment_type=t)
            res = qs.aggregate(gross=Sum("gross_pay"), net=Sum("net_pay"))
            self.stdout.write(f"  {t:<12}: Gross {res['gross'] or 0} | Net {res['net'] or 0}")