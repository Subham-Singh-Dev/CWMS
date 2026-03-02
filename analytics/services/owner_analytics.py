from datetime import timedelta
from calendar import monthrange
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from billing.models import Bill
from expenses.models import Expense
from payroll.models import MonthlySalary
from employees.models import Employee
from payroll.models import Advance
from attendance.models import Attendance


class OwnerAnalyticsService:

    def get_kpis(self, selected_month):
        """
        selected_month: date object (first day of month)
        Returns dict matching King Dashboard KPI variables.
        """

        today = timezone.now().date()

        # -----------------------------
        # Month boundaries
        # -----------------------------
        current_start = selected_month
        last_day = monthrange(selected_month.year, selected_month.month)[1]
        current_end = selected_month.replace(day=last_day)

        previous_month = (selected_month.replace(day=1) - timedelta(days=1)).replace(day=1)
        prev_last_day = monthrange(previous_month.year, previous_month.month)[1]
        previous_end = previous_month.replace(day=prev_last_day)

        # -----------------------------
        # Revenue (Paid Bills)
        # -----------------------------
        current_revenue = Bill.objects.filter(
            is_paid=True,
            paid_on__range=(current_start, current_end)
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        previous_revenue = Bill.objects.filter(
            is_paid=True,
            paid_on__range=(previous_month, previous_end)
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # -----------------------------
        # Expenses
        # -----------------------------
        current_expenses = Expense.objects.filter(
            date__range=(current_start, current_end)
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        previous_expenses = Expense.objects.filter(
            date__range=(previous_month, previous_end)
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # -----------------------------
        # Payroll (Snapshot Based)
        # -----------------------------
        current_payroll = MonthlySalary.objects.filter(
            month=current_start
        ).aggregate(total=Sum("net_pay"))["total"] or Decimal("0.00")

        previous_payroll = MonthlySalary.objects.filter(
            month=previous_month
        ).aggregate(total=Sum("net_pay"))["total"] or Decimal("0.00")

        # -----------------------------
        # Liability (Global)
        # -----------------------------
        unpaid_salary = MonthlySalary.objects.filter(
            is_paid=False
        ).aggregate(total=Sum("net_pay"))["total"] or Decimal("0.00")

        advance_exposure = Advance.objects.filter(
            remaining_amount__gt=0
        ).aggregate(total=Sum("remaining_amount"))["total"] or Decimal("0.00")

        total_liability = unpaid_salary + advance_exposure

        # -----------------------------
        # Workforce
        # -----------------------------
        total_workers = Employee.objects.filter(is_active=True).count()

        new_workers = Employee.objects.filter(
            join_date__range=(current_start, current_end)
        ).count()

        # -----------------------------
        # Attendance Rate
        # -----------------------------
        days_passed = min(today.day, last_day)

        attendance_qs = Attendance.objects.filter(
            date__range=(current_start, current_start.replace(day=days_passed))
        )

        total_present = attendance_qs.filter(status='P').count()
        total_half = attendance_qs.filter(status='H').count()

        total_possible = total_workers * days_passed

        if total_possible > 0:
            attendance_score = total_present + (Decimal("0.5") * total_half)
            attendance_rate = round((attendance_score / total_possible) * 100, 2)
        else:
            attendance_rate = 0

        return {
            "total_revenue": current_revenue,
            "revenue_change": self._percent_change(current_revenue, previous_revenue),
            "total_expenses": current_expenses,
            "expense_change": self._percent_change(current_expenses, previous_expenses),
            "total_payroll": current_payroll,
            "payroll_change": self._percent_change(current_payroll, previous_payroll),
            "total_liability": total_liability,
            "liability_change": 0,  # can compute later if needed
            "total_workers": total_workers,
            "new_workers": new_workers,
            "attendance_rate": attendance_rate,
        }

    def _percent_change(self, current, previous):
        if previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / previous) * 100, 2)