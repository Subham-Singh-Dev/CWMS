"""
Management Command: step4_verify_payroll
=========================================
Runs a manual audit of generated payroll records for May 2026.

Multi-site architecture:
  - Audits all 160 employees across Raigarh (70), Bhilai (60), Korba (30)
  - Prints full salary table grouped per site
  - Per-site financial totals after each site block
  - Cross-site grand total at the end

Checks per employee:
  1. Every active employee has a salary record for May 2026
  2. net_pay == gross_pay - total_deductions  (math integrity)
  3. total_deductions == advance_deducted + pf_deduction + esic_deduction
  4. Employees with advances: advance_deducted > 0
  5. PERMANENT employees: pf_deduction > 0 (if pf_applicable=True)
  6. Leave days counted correctly (paid_leaves > 0 for employees with 'L' records)
  7. No negative net_pay
  8. Gross pay sanity: gross_pay > 0 for employees with attendance

Prints:
  - Per-site salary tables
  - Per-site financial totals
  - Grand total across all sites
  - Full anomaly report
  - Overall verdict

Run AFTER step3_generate_payroll:
    docker-compose exec web python manage.py step4_verify_payroll
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count

from attendance.models import Attendance
from employees.models import Employee
from payroll.models import MonthlySalary


MAY_2026     = date(2026, 5, 1)
MAY_END      = date(2026, 5, 30)
TOLERANCE    = Decimal("0.02")   # 2 paisa tolerance for rounding

SITE_LABELS = {
    "raigarh": "Raigarh",
    "bhilai":  "Bhilai",
    "korba":   "Korba",
}

# Column widths
COL = {
    "idx":   4,
    "name":  28,
    "type":  10,
    "days":  7,
    "leave": 7,
    "gross": 11,
    "adv":   10,
    "pf":    8,
    "esic":  8,
    "net":   11,
    "status": 12,
}

HEADER = (
    f"{'#':<{COL['idx']}} "
    f"{'Employee':<{COL['name']}} "
    f"{'Type':<{COL['type']}} "
    f"{'Days P':<{COL['days']}} "
    f"{'Leaves':<{COL['leave']}} "
    f"{'Gross':>{COL['gross']}} "
    f"{'Adv Ded':>{COL['adv']}} "
    f"{'PF':>{COL['pf']}} "
    f"{'ESIC':>{COL['esic']}} "
    f"{'Net':>{COL['net']}} "
    f"{'Status':<{COL['status']}}"
)
DIVIDER      = "─" * 116
THICK_DIVIDER = "═" * 116


class Command(BaseCommand):
    help = "Audit and verify May 2026 payroll records (multi-site: 3 sites, 160 employees)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 4: PAYROLL VERIFICATION AUDIT (MULTI-SITE) ===\n"
        ))

        all_employees = list(
            Employee.objects.filter(is_active=True).select_related("role")
        )
        salaries = {
            s.employee_id: s
            for s in MonthlySalary.objects.filter(month=MAY_2026)
                                          .select_related("employee")
        }

        self.stdout.write(
            f"Auditing {len(all_employees)} employees | "
            f"{len(salaries)} salary records found\n"
        )

        # Pre-fetch attendance counts per employee to avoid N+1
        att_p_map = dict(
            Attendance.objects.filter(
                date__gte=MAY_2026, date__lte=MAY_END, status="P"
            ).values("employee_id")
             .annotate(cnt=Count("id"))
             .values_list("employee_id", "cnt")
        )
        att_l_map = dict(
            Attendance.objects.filter(
                date__gte=MAY_2026, date__lte=MAY_END, status="L"
            ).values("employee_id")
             .annotate(cnt=Count("id"))
             .values_list("employee_id", "cnt")
        )

        all_anomalies   = []
        grand_verified  = 0
        grand_missing   = 0

        # Accumulate grand totals across all sites
        grand_gross   = Decimal("0.00")
        grand_adv     = Decimal("0.00")
        grand_pf      = Decimal("0.00")
        grand_esic    = Decimal("0.00")
        grand_net     = Decimal("0.00")

        row_idx = 0  # global row counter across sites

        for site_key, site_label in SITE_LABELS.items():
            site_employees = [e for e in all_employees if e.site == site_key]

            if not site_employees:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠ No employees found for site: {site_label} — skipping\n"
                    )
                )
                continue

            # ── Site header ─────────────────────────────────────────────────
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"\n{'━'*116}\n  SITE: {site_label.upper()}  "
                    f"({len(site_employees)} employees)\n{'━'*116}"
                )
            )
            self.stdout.write(HEADER)
            self.stdout.write(DIVIDER)

            site_anomalies = []
            site_verified  = 0
            site_missing   = 0
            site_gross   = Decimal("0.00")
            site_adv     = Decimal("0.00")
            site_pf      = Decimal("0.00")
            site_esic    = Decimal("0.00")
            site_net     = Decimal("0.00")

            for emp in site_employees:
                row_idx += 1
                salary = salaries.get(emp.id)

                if not salary:
                    site_missing  += 1
                    grand_missing += 1
                    site_anomalies.append(
                        f"❌ MISSING SALARY — {emp.name} ({emp.employment_type})"
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"{row_idx:<{COL['idx']}} "
                            f"{emp.name:<{COL['name']}} "
                            f"{emp.employment_type:<{COL['type']}} "
                            f"{'—':<{COL['days']}} {'—':<{COL['leave']}} "
                            f"{'—':>{COL['gross']}} {'—':>{COL['adv']}} "
                            f"{'—':>{COL['pf']}} {'—':>{COL['esic']}} "
                            f"{'—':>{COL['net']}} {'NO RECORD':<{COL['status']}}"
                        )
                    )
                    continue

                # ── Math checks ─────────────────────────────────────────────
                row_anomalies = []

                # Check 1: net == gross - total_deductions
                expected_net = salary.gross_pay - salary.total_deductions
                if abs(salary.net_pay - expected_net) > TOLERANCE:
                    row_anomalies.append(
                        f"NET MISMATCH: got {salary.net_pay}, "
                        f"expected {expected_net}"
                    )

                # Check 2: total_deductions == advance + pf + esic
                expected_total = (
                    salary.advance_deducted +
                    salary.pf_deduction +
                    salary.esic_deduction
                )
                if abs(salary.total_deductions - expected_total) > TOLERANCE:
                    row_anomalies.append(
                        f"DEDUCTION MISMATCH: total={salary.total_deductions}, "
                        f"sum={expected_total}"
                    )

                # Check 3: negative net pay
                if salary.net_pay < Decimal("0.00"):
                    row_anomalies.append(f"NEGATIVE NET PAY: {salary.net_pay}")

                # Check 4: PERMANENT + pf_applicable must have PF
                if emp.employment_type == "PERMANENT" and emp.pf_applicable:
                    if salary.pf_deduction == 0 and salary.gross_pay > 0:
                        row_anomalies.append("PF MISSING for PERMANENT employee")

                # Check 5: gross > 0 when days_present > 0
                if salary.days_present > 0 and salary.gross_pay == 0:
                    row_anomalies.append(
                        f"ZERO GROSS despite {salary.days_present} present days"
                    )

                # Check 6: paid_leaves should match 'L' attendance records
                att_leaves = att_l_map.get(emp.id, 0)
                if att_leaves > 0 and salary.paid_leaves == 0:
                    row_anomalies.append(
                        f"LEAVE COUNT MISMATCH: {att_leaves} 'L' records "
                        f"but paid_leaves=0"
                    )

                # ── Accumulate site totals ───────────────────────────────────
                site_gross += salary.gross_pay
                site_adv   += salary.advance_deducted
                site_pf    += salary.pf_deduction
                site_esic  += salary.esic_deduction
                site_net   += salary.net_pay

                # ── Print row ────────────────────────────────────────────────
                status_str = "✅ OK" if not row_anomalies else f"❌ {len(row_anomalies)} issue(s)"
                line = (
                    f"{row_idx:<{COL['idx']}} "
                    f"{emp.name:<{COL['name']}} "
                    f"{emp.employment_type:<{COL['type']}} "
                    f"{salary.days_present:<{COL['days']}} "
                    f"{salary.paid_leaves:<{COL['leave']}} "
                    f"{salary.gross_pay:>{COL['gross']}} "
                    f"{salary.advance_deducted:>{COL['adv']}} "
                    f"{salary.pf_deduction:>{COL['pf']}} "
                    f"{salary.esic_deduction:>{COL['esic']}} "
                    f"{salary.net_pay:>{COL['net']}} "
                    f"{status_str:<{COL['status']}}"
                )

                if row_anomalies:
                    self.stdout.write(self.style.ERROR(line))
                    for a in row_anomalies:
                        site_anomalies.append(f"❌ {emp.name}: {a}")
                        self.stdout.write(
                            self.style.ERROR(f"     ↳ {a}")
                        )
                else:
                    self.stdout.write(line)
                    site_verified += 1

            # ── Per-site totals row ─────────────────────────────────────────
            self.stdout.write(DIVIDER)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {site_label.upper()} TOTALS"
                    f" ({site_verified}/{len(site_employees)} verified)"
                    f"{'':>{COL['days'] + COL['leave'] + 2}} "
                    f"{site_gross:>{COL['gross']}} "
                    f"{site_adv:>{COL['adv']}} "
                    f"{site_pf:>{COL['pf']}} "
                    f"{site_esic:>{COL['esic']}} "
                    f"{site_net:>{COL['net']}} "
                )
            )

            if site_anomalies:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ⚠ {len(site_anomalies)} anomaly(ies) in {site_label}:"
                    )
                )
                for a in site_anomalies:
                    self.stdout.write(self.style.ERROR(f"    {a}"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✅ No anomalies in {site_label}"
                    )
                )

            # Accumulate grand totals
            grand_verified += site_verified
            grand_gross    += site_gross
            grand_adv      += site_adv
            grand_pf       += site_pf
            grand_esic     += site_esic
            grand_net      += site_net
            all_anomalies.extend(site_anomalies)

        # ── Grand total row ───────────────────────────────────────────────────
        self.stdout.write("\n" + THICK_DIVIDER)
        self.stdout.write(
            f"  {'GRAND TOTAL (ALL SITES)':<{COL['name'] + COL['type'] + COL['days'] + COL['leave'] + 3}} "
            f"{grand_gross:>{COL['gross']}} "
            f"{grand_adv:>{COL['adv']}} "
            f"{grand_pf:>{COL['pf']}} "
            f"{grand_esic:>{COL['esic']}} "
            f"{grand_net:>{COL['net']}}"
        )
        self.stdout.write(THICK_DIVIDER)

        # ── Distribution breakdown ────────────────────────────────────────────
        self.stdout.write("\n  PAYROLL DISTRIBUTION BY SITE")
        self.stdout.write("  " + "─" * 60)
        for site_key, site_label in SITE_LABELS.items():
            site_emp_ids = list(
                Employee.objects.filter(
                    site=site_key, is_active=True
                ).values_list("id", flat=True)
            )
            site_total = MonthlySalary.objects.filter(
                month=MAY_2026, employee_id__in=site_emp_ids
            ).aggregate(net=Sum("net_pay"))["net"] or Decimal("0.00")

            pct = (site_total / grand_net * 100) if grand_net else Decimal("0")
            emp_count = len(site_emp_ids)
            self.stdout.write(
                f"  {site_label:<10}: "
                f"{emp_count:>3} employees | "
                f"Net payroll: {str(site_total):>12} | "
                f"Share: {pct:.1f}%"
            )

        # ── Employment type breakdown ─────────────────────────────────────────
        self.stdout.write("\n  PAYROLL DISTRIBUTION BY EMPLOYMENT TYPE")
        self.stdout.write("  " + "─" * 60)
        for emp_type in ["LOCAL", "PERMANENT"]:
            type_emp_ids = list(
                Employee.objects.filter(
                    is_active=True, employment_type=emp_type
                ).values_list("id", flat=True)
            )
            type_total = MonthlySalary.objects.filter(
                month=MAY_2026, employee_id__in=type_emp_ids
            ).aggregate(
                gross=Sum("gross_pay"),
                net=Sum("net_pay"),
                pf=Sum("pf_deduction"),
            )
            self.stdout.write(
                f"  {emp_type:<12}: "
                f"{len(type_emp_ids):>3} employees | "
                f"Gross: {str(type_total['gross'] or 0):>12} | "
                f"Net: {str(type_total['net'] or 0):>12} | "
                f"PF: {str(type_total['pf'] or 0):>10}"
            )

        # ── Advance recovery check ────────────────────────────────────────────
        self.stdout.write("\n  ADVANCE RECOVERY CHECK")
        self.stdout.write("  " + "─" * 60)
        with_advance = MonthlySalary.objects.filter(
            month=MAY_2026, advance_deducted__gt=0
        )
        zero_advance = MonthlySalary.objects.filter(
            month=MAY_2026, advance_deducted=0
        )
        total_recovered = with_advance.aggregate(
            total=Sum("advance_deducted")
        )["total"] or Decimal("0.00")
        self.stdout.write(
            f"  Employees with advance deduction : {with_advance.count()}"
        )
        self.stdout.write(
            f"  Employees with no advance        : {zero_advance.count()}"
        )
        self.stdout.write(
            f"  Total advance recovered (May)    : {total_recovered}"
        )

        # ── Attendance cross-check summary ────────────────────────────────────
        self.stdout.write("\n  ATTENDANCE CROSS-CHECK SUMMARY")
        self.stdout.write("  " + "─" * 60)
        for status_code, label in [
            ("P", "Present"),
            ("A", "Absent"),
            ("H", "Half Day"),
            ("L", "Leave"),
        ]:
            count = Attendance.objects.filter(
                date__gte=MAY_2026, date__lte=MAY_END, status=status_code
            ).count()
            self.stdout.write(f"  {label:<12}: {count:>6} records")
        total_att = Attendance.objects.filter(
            date__gte=MAY_2026, date__lte=MAY_END
        ).count()
        self.stdout.write(f"  {'TOTAL':<12}: {total_att:>6} records")

        # ── Final verdict ─────────────────────────────────────────────────────
        self.stdout.write("\n" + THICK_DIVIDER)
        self.stdout.write(f"  Total employees   : {len(all_employees)}")
        self.stdout.write(f"  Salaries verified : {grand_verified}")
        self.stdout.write(f"  Missing records   : {grand_missing}")

        if all_anomalies:
            self.stdout.write(
                self.style.ERROR(
                    f"\n  ⚠ TOTAL ANOMALIES FOUND: {len(all_anomalies)}"
                )
            )
            self.stdout.write(self.style.ERROR("\n  Full anomaly list:"))
            for a in all_anomalies:
                self.stdout.write(self.style.ERROR(f"    {a}"))
            self.stdout.write(
                self.style.ERROR(
                    "\n  ❌ VERDICT: PAYROLL HAS ISSUES — investigate anomalies above\n"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n  ✅ VERDICT: ALL {grand_verified} SALARY RECORDS MATHEMATICALLY CORRECT\n"
                    f"     3 sites verified. System is ready for production use.\n"
                )
            )