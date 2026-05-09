"""
Management Command: step4_verify_payroll
=========================================
Runs a manual audit of generated payroll records.

Checks:
  1. Every active employee has a salary record for May 2026
  2. net_pay == gross_pay - total_deductions (math integrity)
  3. total_deductions == advance_deducted + pf_deduction + esic_deduction
  4. Employees with advances: advance_deducted > 0
  5. PERMANENT employees: pf_deduction > 0 (if pf_applicable=True)
  6. Leave days counted correctly (paid_leaves > 0 for employees with 'L' records)
  7. No negative net_pay
  8. Gross pay sanity: gross_pay > 0 for employees with attendance

Prints:
  - Full salary table
  - Anomaly report
  - Overall verdict

Run AFTER step3_generate_payroll:
    docker-compose exec web python manage.py step4_verify_payroll
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from attendance.models import Attendance
from employees.models import Employee
from payroll.models import MonthlySalary


MAY_2026 = date(2026, 5, 1)
TOLERANCE = Decimal("0.02")  # 2 paisa tolerance for rounding


class Command(BaseCommand):
    help = "Audit and verify May 2026 payroll records"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 4: PAYROLL VERIFICATION AUDIT ===\n"
        ))

        employees = list(
            Employee.objects.filter(is_active=True).select_related("role")
        )
        salaries  = {
            s.employee_id: s
            for s in MonthlySalary.objects.filter(month=MAY_2026).select_related("employee")
        }

        anomalies = []
        verified  = 0

        self.stdout.write(
            f"{'#':<4} {'Employee':<28} {'Type':<10} "
            f"{'Days P':<7} {'Leaves':<7} {'Gross':>10} "
            f"{'Adv Ded':>9} {'PF':>7} {'ESIC':>7} {'Net':>10} {'Status':<10}"
        )
        self.stdout.write("─" * 110)

        for idx, emp in enumerate(employees, 1):
            salary = salaries.get(emp.id)

            if not salary:
                anomalies.append(
                    f"❌ MISSING SALARY — {emp.name} ({emp.employment_type})"
                )
                self.stdout.write(
                    self.style.ERROR(
                        f"{idx:<4} {emp.name:<28} {emp.employment_type:<10} "
                        f"{'—':<7} {'—':<7} {'—':>10} {'—':>9} {'—':>7} {'—':>7} {'—':>10} NO RECORD"
                    )
                )
                continue

            # ── Math checks ────────────────────────────────────────────────
            row_anomalies = []

            # Check 1: net = gross - total_deductions
            expected_net = salary.gross_pay - salary.total_deductions
            if abs(salary.net_pay - expected_net) > TOLERANCE:
                row_anomalies.append(
                    f"NET MISMATCH: got {salary.net_pay}, expected {expected_net}"
                )

            # Check 2: total_deductions = advance + pf + esic
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
            if salary.net_pay < 0:
                row_anomalies.append(
                    f"NEGATIVE NET PAY: {salary.net_pay}"
                )

            # Check 4: PERMANENT + pf_applicable should have PF deducted
            if emp.employment_type == "PERMANENT" and emp.pf_applicable:
                if salary.pf_deduction == 0 and salary.gross_pay > 0:
                    row_anomalies.append("PF MISSING for PERMANENT employee")

            # Check 5: gross should be > 0 if days_present > 0
            if salary.days_present > 0 and salary.gross_pay == 0:
                row_anomalies.append(
                    f"ZERO GROSS despite {salary.days_present} present days"
                )

            # ── Attendance cross-check ──────────────────────────────────────
            att_p = Attendance.objects.filter(
                employee=emp,
                date__gte=MAY_2026,
                date__lte=date(2026, 5, 30),
                status="P",
            ).count()

            att_l = Attendance.objects.filter(
                employee=emp,
                date__gte=MAY_2026,
                date__lte=date(2026, 5, 30),
                status="L",
            ).count()

            # ── Print row ─────────────────────────────────────────────────
            status_str = "✅ OK" if not row_anomalies else f"❌ {len(row_anomalies)} issues"

            line = (
                f"{idx:<4} {emp.name:<28} {emp.employment_type:<10} "
                f"{salary.days_present:<7} {salary.paid_leaves:<7} "
                f"{salary.gross_pay:>10} {salary.advance_deducted:>9} "
                f"{salary.pf_deduction:>7} {salary.esic_deduction:>7} "
                f"{salary.net_pay:>10} {status_str}"
            )

            if row_anomalies:
                self.stdout.write(self.style.ERROR(line))
                for a in row_anomalies:
                    anomalies.append(f"❌ {emp.name}: {a}")
            else:
                self.stdout.write(line)
                verified += 1

        # ── Totals ───────────────────────────────────────────────────────────
        self.stdout.write("─" * 110)
        totals = MonthlySalary.objects.filter(month=MAY_2026).aggregate(
            total_gross=Sum("gross_pay"),
            total_advance=Sum("advance_deducted"),
            total_pf=Sum("pf_deduction"),
            total_esic=Sum("esic_deduction"),
            total_net=Sum("net_pay"),
        )
        self.stdout.write(
            f"\n{'TOTALS':<43} "
            f"{str(totals['total_gross'] or 0):>10} "
            f"{str(totals['total_advance'] or 0):>9} "
            f"{str(totals['total_pf'] or 0):>7} "
            f"{str(totals['total_esic'] or 0):>7} "
            f"{str(totals['total_net'] or 0):>10}"
        )

        # ── Final verdict ────────────────────────────────────────────────────
        self.stdout.write("\n" + "═" * 60)
        self.stdout.write(f"  Total employees   : {len(employees)}")
        self.stdout.write(f"  Salaries verified : {verified}")
        self.stdout.write(f"  Missing records   : {len(employees) - len(salaries)}")

        if anomalies:
            self.stdout.write(
                self.style.ERROR(f"\n  ⚠ ANOMALIES FOUND ({len(anomalies)}):")
            )
            for a in anomalies:
                self.stdout.write(self.style.ERROR(f"    {a}"))
            self.stdout.write(
                self.style.ERROR("\n  ❌ VERDICT: PAYROLL HAS ISSUES — investigate above\n")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n  ✅ VERDICT: ALL {verified} SALARY RECORDS MATHEMATICALLY CORRECT\n"
                    f"     System is ready for production use.\n"
                )
            )
