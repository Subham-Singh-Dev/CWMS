"""Payroll view handlers.

Module: payroll.views
App: payroll
Purpose: Manager-facing payroll orchestration, list/report rendering, and
payslip exports.
Key responsibilities: Payroll summaries, salary list actions, payslip exports,
and advance issuance/registers.
Dependencies: payroll.services for write-side financial logic, employee and
portal auth layers, and PDF rendering utilities.
Author note: Views delegate calculations to services to avoid duplicated money
logic.
"""

# ============================================================
# IMPORTS
# ============================================================
import csv
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from django.views.decorators.http import require_POST

try:
    from xhtml2pdf import pisa  # type: ignore[reportMissingImports]
except ImportError:
    pisa = None

from employees.models import Employee
from payroll.services import SalaryAlreadyGeneratedError, generate_monthly_salary

def _cache_delete_pattern(pattern: str) -> None:
    from config.cache_utils import delete_pattern as _delete_pattern
    try:
        _delete_pattern(pattern)
    except Exception:
        pass
from portal.decorators import manager_required

from .models import Advance, MonthlySalary
from .services import issue_advance


# ============================================================
# PAYSLIP EXPORTS
# ============================================================
@login_required
def download_payslip(request, salary_id):
    """Generate/download a single payslip PDF with strict authorization checks.

    Args:
        request (HttpRequest): Requesting user.
        salary_id (int): MonthlySalary id.

    Returns:
        HttpResponse: PDF response for the payslip.

    Raises:
        PermissionDenied: When the user is not authorized.

    Business Rule:
        Only managers or the owning worker can access a paid payslip.
    """
    # Reason: Reduce DB hits during PDF rendering.
    salary = get_object_or_404(
        MonthlySalary.objects.select_related('employee'),
        id=salary_id,
    )

    # Reason: Only privileged roles can bypass worker ownership checks.
    if request.user.is_superuser or request.user.is_staff:
        pass
    elif hasattr(request.user, 'employee'):
        # Reason: Enforce worker ownership to prevent ID guessing.
        if salary.employee != request.user.employee:
            raise PermissionDenied(
                "⛔ You are not authorized to view this payslip."
            )

        # Reason: Payslips are available only after salary is paid.
        if not salary.is_paid:
            raise PermissionDenied("⏳ Payslip not available until salary is paid.")
    else:
        raise PermissionDenied("Unauthorized access.")

    template_path = 'payroll/payslip_pdf.html'
    context = {'salary': salary}
    response = HttpResponse(content_type='application/pdf')
    filename = (
        f"Payslip_{salary.employee.name}_"
        f"{salary.month.strftime('%b_%Y')}.pdf"
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')

    return response

# ============================================================
# PAYROLL SUMMARY
# ============================================================
@manager_required
def payroll_batch_summary(request, viewing_as_owner=False):
    """Render payroll batch summary with month roll-forward behavior.

    Args:
        request (HttpRequest): Incoming request.
        viewing_as_owner (bool): Owner read-only flag propagated by decorator.

    Returns:
        HttpResponse: Payroll batch summary page.

    Raises:
        Http404: When the month format is invalid.

    Business Rule:
        If the current month has no payroll, fall back to the previous month.
    """
    today = date.today()
    current_month_str = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    # Reason: Ensure the summary always shows a valid month.
    selected_month = request.GET.get("month")

    if not selected_month:
        month_to_check = current_month_str
        check_date = datetime.strptime(month_to_check, "%Y-%m").date()
        if not MonthlySalary.objects.filter(
            month__year=check_date.year,
            month__month=check_date.month
        ).exists():
            selected_month = prev_month
        else:
            selected_month = month_to_check

    try:
        month_date = datetime.strptime(selected_month, "%Y-%m").date()
    except ValueError:
        raise Http404("Invalid month format. Expected YYYY-MM")

    # Reason: Scope all aggregations to the selected month.
    salaries_qs = MonthlySalary.objects.filter(
        month__year=month_date.year,
        month__month=month_date.month
    )

    def shift_month(base_month, delta):
        """Shift a month anchor by delta months while preserving day=1 semantics."""
        idx = (base_month.year * 12 + base_month.month - 1) + delta
        year = idx // 12
        month = (idx % 12) + 1
        return date(year, month, 1)

    months_6 = [
        shift_month(month_date.replace(day=1), -i) for i in range(5, -1, -1)
    ]
    months_12 = [
        shift_month(month_date.replace(day=1), -i) for i in range(11, -1, -1)
    ]

    trend_start = months_12[0]
    trend_end = shift_month(month_date.replace(day=1), 1)

    deduction_expr = ExpressionWrapper(
        F("advance_deducted") + F("pf_deduction") + F("esic_deduction"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    # Reason: Trend series powers the dashboard charts.
    trend_qs = (
        MonthlySalary.objects
        .filter(month__gte=trend_start, month__lt=trend_end)
        .values("month")
        .annotate(
            total_gross=Coalesce(Sum("gross_pay"), Decimal("0.00")),
            total_deductions=Coalesce(Sum(deduction_expr), Decimal("0.00")),
            total_net=Coalesce(Sum("net_pay"), Decimal("0.00")),
            unpaid_liability=Coalesce(
                Sum("net_pay", filter=Q(is_paid=False)), Decimal("0.00")
            ),
        )
    )

    trend_map = {item["month"]: item for item in trend_qs}

    def build_chart_series(month_points):
        """Build chart-ready label/value arrays for monthly payroll trend cards."""
        labels = []
        gross = []
        deductions = []
        net = []
        liability = []

        for point in month_points:
            labels.append(point.strftime("%b %y"))
            data = trend_map.get(point)
            gross.append(float(data["total_gross"]) if data else 0.0)
            deductions.append(float(data["total_deductions"]) if data else 0.0)
            net.append(float(data["total_net"]) if data else 0.0)
            liability.append(float(data["unpaid_liability"]) if data else 0.0)

        return {
            "labels": labels,
            "gross": gross,
            "deductions": deductions,
            "net": net,
            "liability": liability,
        }

    chart_6 = build_chart_series(months_6)
    chart_12 = build_chart_series(months_12)

    year_start = date(month_date.year, 1, 1)
    months_year = [
        date(month_date.year, m, 1) for m in range(1, month_date.month + 1)
    ]
    trend_year_qs = (
        MonthlySalary.objects
        .filter(month__gte=year_start, month__lt=trend_end)
        .values("month")
        .annotate(
            total_gross=Coalesce(Sum("gross_pay"), Decimal("0.00")),
            total_deductions=Coalesce(Sum(deduction_expr), Decimal("0.00")),
            total_net=Coalesce(Sum("net_pay"), Decimal("0.00")),
            unpaid_liability=Coalesce(
                Sum("net_pay", filter=Q(is_paid=False)), Decimal("0.00")
            ),
        )
    )
    trend_year_map = {item["month"]: item for item in trend_year_qs}

    chart_year = {
        "labels": [point.strftime("%b") for point in months_year],
        "gross": [
            float(trend_year_map.get(point, {}).get("total_gross", 0.0))
            for point in months_year
        ],
        "deductions": [
            float(trend_year_map.get(point, {}).get("total_deductions", 0.0))
            for point in months_year
        ],
        "net": [
            float(trend_year_map.get(point, {}).get("total_net", 0.0))
            for point in months_year
        ],
        "liability": [
            float(trend_year_map.get(point, {}).get("unpaid_liability", 0.0))
            for point in months_year
        ],
    }

    batch_generated_at = salaries_qs.order_by("generated_at").values_list(
        "generated_at", flat=True
    ).first()

    # Reason: Exclude future months from the selector.
    all_months_raw = (
        MonthlySalary.objects
        .values_list("month", flat=True)
        .distinct()
        .order_by("-month")
    )

    current_date = date.today()
    available_months_list = []
    for m in all_months_raw:
        if m.year < current_date.year or (
            m.year == current_date.year and m.month <= current_date.month
        ):
            month_str = m.strftime("%Y-%m")
            month_display_name = m.strftime("%B %Y")
            available_months_list.append(
                {"value": month_str, "display": month_display_name}
            )
            if len(available_months_list) >= 12:
                break

    available_months = available_months_list

    if not salaries_qs.exists():
        context = {
            "selected_month": selected_month,
            "available_months": available_months,
            "current_month_str": current_month_str,
            "prev_month_str": prev_month,
            "month_display": datetime.strptime(
                selected_month, "%Y-%m"
            ).strftime("%B %Y"),
            "has_payroll": False,
        }
        return render(
            request,
            "payroll/payroll_batch_summary.html",
            context
        )

    # Reason: Aggregate once to reduce template-side calculations.
    aggregates = salaries_qs.aggregate(
        total_employees=Count("id"),
        total_gross=Coalesce(Sum("gross_pay"), Decimal("0.00")),
        total_advance_deducted=Coalesce(Sum("advance_deducted"), Decimal("0.00")),
        total_pf_deduction=Coalesce(Sum("pf_deduction"), Decimal("0.00")),
        total_esic_deduction=Coalesce(Sum("esic_deduction"), Decimal("0.00")),
        total_deductions=Coalesce(Sum(deduction_expr), Decimal("0.00")),
        total_net=Coalesce(Sum("net_pay"), Decimal("0.00")),
        paid_count=Count("id", filter=Q(is_paid=True)),
        unpaid_count=Count("id", filter=Q(is_paid=False)),
    )
    
    unpaid_liability = salaries_qs.filter(is_paid=False).aggregate(
        liability=Coalesce(Sum("net_pay"), Decimal("0.00"))
    )["liability"]

    context = {
        "selected_month": selected_month,
        "month_display": datetime.strptime(
            selected_month, "%Y-%m"
        ).strftime("%B %Y"),
        "available_months": available_months,
        "current_month_str": current_month_str,
        "prev_month_str": prev_month,
        "total_employees": aggregates["total_employees"],
        "paid_count": aggregates["paid_count"],
        "unpaid_count": aggregates["unpaid_count"],
        "total_gross": aggregates["total_gross"],
        "total_advance_deducted": aggregates["total_advance_deducted"],
        "total_pf_deduction": aggregates["total_pf_deduction"],
        "total_esic_deduction": aggregates["total_esic_deduction"],
        "total_deductions": aggregates["total_deductions"],
        "total_net": aggregates["total_net"],
        "total_liability": unpaid_liability,
        "generated_at": batch_generated_at,
        "has_payroll": True,
        "chart_6": json.dumps(chart_6),
        "chart_12": json.dumps(chart_12),
        "chart_year": json.dumps(chart_year),
    }
    
    return render(
        request,
        "payroll/payroll_batch_summary.html",
        context
    )


# ============================================================
# SALARY LIST ACTIONS
# ============================================================
@manager_required
def salary_list_view(request):
    """Show employee-wise salary generation status for a selected month.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Salary list page with generation status.

    Raises:
        Http404: When the month format is invalid.

    Business Rule:
        Defaults to the current month when no month is selected.
    """
    selected_month = request.GET.get("month")

    if not selected_month:
        today = timezone.now().date()
        month_date = today.replace(day=1)
        selected_month = month_date.strftime("%Y-%m")

    try:
        month_date = datetime.strptime(selected_month, "%Y-%m").date()
    except ValueError:
        raise Http404("Invalid month format")

    employees = Employee.objects.select_related("user").all()

    salaries = MonthlySalary.objects.filter(
        month__year=month_date.year,
        month__month=month_date.month
    ).select_related("employee")

    salary_map = {s.employee_id: s for s in salaries}

    rows = []
    for employee in employees:
        rows.append(
            {
                "employee": employee,
                "salary": salary_map.get(employee.id),
            }
        )

    context = {
        "selected_month": selected_month,
        "selected_month_display": month_date.strftime("%B %Y"),
        "rows": rows,
    }

    return render(
        request,
        "payroll/salary_list.html",
        context
    )

@manager_required
@require_POST
def generate_employee_salary(request):
    """Generate payroll for one employee-month and return with status messaging.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Redirect back to salary list with status messaging.

    Raises:
        Http404: When required inputs are missing or invalid.

    Business Rule:
        Payroll generation is delegated to the service layer.
    """
    employee_id = request.POST.get("employee_id")
    selected_month = request.POST.get("month")

    if not employee_id or not selected_month:
        raise Http404("Invalid request")

    try:
        month_date = datetime.strptime(selected_month, "%Y-%m").date()
    except ValueError:
        raise Http404("Invalid month format")

    employee = get_object_or_404(Employee, id=employee_id)

    timestamp = timezone.now().strftime("%d %b %Y %H:%M")

    try:
        salary = generate_monthly_salary(employee, month_date)

        if salary is None:
            messages.warning(
                request,
                f"⚠️ Salary not generated for {employee.name} — "
                f"no payable attendance for {selected_month} "
                f"({timestamp})"
            )
        else:
            messages.success(
                request,
                f"✅ Salary generated for {employee.name} "
                f"({selected_month}) at {timestamp}"
            )

    except SalaryAlreadyGeneratedError:
        messages.warning(
            request,
            f"⚠️ Salary already generated for {employee.name}"
        )

    except Exception as exc:
        messages.error(
            request,
            f"❌ Failed to generate salary for {employee.name}: {exc}"
        )

    salary_list_url = f"{reverse('manager_salary_list')}?month={selected_month}"
    return redirect(salary_list_url)

@manager_required
@require_POST
def mark_salary_paid(request):
    """Mark one generated salary row as paid with idempotency guard.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Redirect back to salary list with status message.

    Raises:
        Http404: When required inputs are missing.

    Business Rule:
        Paid salaries are idempotent and should not be re-marked.
    """
    salary_id = request.POST.get("salary_id")
    selected_month = request.POST.get("month")

    if not salary_id or not selected_month:
        raise Http404("Invalid request")

    salary = get_object_or_404(MonthlySalary, id=salary_id)

    # Reason: Prevent duplicate paid markers and audit confusion.
    if salary.is_paid:
        messages.warning(
            request,
            f"⚠️ Salary already marked as paid for {salary.employee.name}"
        )
        salary_list_url = f"{reverse('manager_salary_list')}?month={selected_month}"
        return redirect(salary_list_url)

    salary.is_paid = True
    salary.paid_on = timezone.now()
    salary.save(update_fields=["is_paid", "paid_on"])

    timestamp = salary.paid_on.strftime("%d %b %Y %H:%M")

    messages.success(
        request,
        f"✅ Salary marked as PAID for {salary.employee.name} "
        f"at {timestamp}"
    )

    salary_list_url = f"{reverse('manager_salary_list')}?month={selected_month}"
    return redirect(salary_list_url)

@manager_required
def export_salary_list_csv(request):
    """Export selected month salary register as downloadable CSV.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: CSV download response.

    Raises:
        Http404: When the month parameter is missing or invalid.

    Business Rule:
        Export is scoped to the selected month only.
    """
    selected_month = request.GET.get("month")

    if not selected_month:
        raise Http404("Month required")

    try:
        month_date = datetime.strptime(selected_month, "%Y-%m").date()
    except ValueError:
        raise Http404("Invalid month format")

    salaries = (
        MonthlySalary.objects
        .select_related("employee")
        .filter(month=month_date)
        .order_by("employee__name")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="salary_list_{selected_month}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        [
            "Employee Name",
            "Employment Type",
            "Gross Pay",
            "Advance Deducted",
            "PF Deduction",
            "ESIC Deduction",
            "Total Deductions",
            "Net Pay",
            "Status",
            "Paid On",
        ]
    )

    for salary in salaries:
        writer.writerow(
            [
                salary.employee.name,
                salary.employee.employment_type,
                salary.gross_pay,
                salary.advance_deducted,
                salary.pf_deduction,
                salary.esic_deduction,
                salary.total_deductions,
                salary.net_pay,
                "Paid" if salary.is_paid else "Unpaid",
                salary.paid_on.strftime("%d-%b-%Y %H:%M")
                if salary.paid_on
                else "",
            ]
        )

    return response

# ============================================================
# ISSUE ADVANCE VIEW
# ============================================================
# PURPOSE:
# Manager-facing endpoint to issue cash advance to employees.
#
# ARCHITECTURAL RULE:
# - This view MUST NOT contain financial calculations.
# - All financial logic MUST live in payroll/services.py.
# - This view only validates input and delegates to service layer.
#
# SECURITY:
# - Protected by @login_required
# - Protected by @manager_required
# - Only active employees are selectable
# ==========================================================

@login_required
@manager_required
def issue_advance_view(request):
    """Create employee advance records by delegating finance logic.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Rendered issue-advance form or success state.

    Raises:
        ValidationError: When the advance data is invalid.

    Business Rule:
        All advance calculations must live in the service layer.
    """
    # Reason: Only active employees can receive advances.
    employees = Employee.objects.filter(is_active=True)

    if request.method == "POST":

        employee_id = request.POST.get("employee")
        amount = request.POST.get("amount")
        issued_date = request.POST.get("issued_date")

        try:
            employee = Employee.objects.get(id=employee_id)

            issue_advance(employee, amount, issued_date)

            from config.cache_utils import delete_patterns
            delete_patterns([
                "api:advances:*",
                "advance:register:*",
                "dashboard:manager:*",
                "dashboard:king:*",
            ])

            return render(
                request,
                "payroll/issue_advance.html",
                {
                    "employees": employees,
                    "success": "Advance issued successfully.",
                    "viewing_as_owner": request.viewing_as_owner,
                }
            )

        except ValidationError as e:
            return render(
                request,
                "payroll/issue_advance.html",
                {
                    "employees": employees,
                    "error": str(e),
                    "viewing_as_owner": request.viewing_as_owner,
                }
            )

    return render(
        request,
        "payroll/issue_advance.html",
        {
            "employees": employees,
            "today": timezone.now().date(),
            "viewing_as_owner": request.viewing_as_owner,
        }
    )


@login_required
@manager_required
def advance_register_view(request):
    """Render manager/owner advance register with filters and pagination.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Advance register page with filters and totals.

    Raises:
        None.

    Business Rule:
        Filters are applied before pagination to keep totals accurate.
    """
    # Reason: Select related data for list rendering without extra queries.
    cache_key = (
        f"advance:register:{request.user.id}:"
        f"{request.session.session_key or 'anon'}:"
        f"{request.GET.urlencode()}"
    )
    cached_html = cache.get(cache_key)
    if cached_html:
        return HttpResponse(cached_html)

    advances_qs = Advance.objects.select_related(
        "employee", "employee__user"
    ).all()

    search = (request.GET.get("search") or "").strip()
    status = (request.GET.get("status") or "all").strip().lower()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if search:
        advances_qs = advances_qs.filter(
            Q(employee__name__icontains=search)
            | Q(employee__user__username__icontains=search)
        )

    if status == "outstanding":
        advances_qs = advances_qs.filter(remaining_amount__gt=0)
    elif status == "settled":
        advances_qs = advances_qs.filter(remaining_amount=0)

    if date_from:
        advances_qs = advances_qs.filter(issued_date__gte=date_from)
    if date_to:
        advances_qs = advances_qs.filter(issued_date__lte=date_to)

    advances_qs = advances_qs.order_by("-issued_date", "-created_at")

    totals = advances_qs.aggregate(
        total_issued=Coalesce(Sum("amount"), Decimal("0.00")),
        total_outstanding=Coalesce(Sum("remaining_amount"), Decimal("0.00")),
        total_records=Count("id"),
        settled_count=Count("id", filter=Q(remaining_amount=0)),
        outstanding_employee_count=Count(
            "employee_id", filter=Q(remaining_amount__gt=0), distinct=True
        ),
    )

    page_size = 25
    page_number = request.GET.get("page", 1)
    paginator = Paginator(advances_qs, page_size)
    page_obj = paginator.get_page(page_number)

    context = {
        "advances": page_obj,
        "page_obj": page_obj,
        "search": search,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "total_issued": totals["total_issued"],
        "total_outstanding": totals["total_outstanding"],
        "total_records": totals["total_records"],
        "settled_count": totals["settled_count"],
        "outstanding_employee_count": totals["outstanding_employee_count"],
        "viewing_as_owner": request.viewing_as_owner,
    }
    html = render_to_string("payroll/advance_register.html", context, request=request)
    cache.set(cache_key, html, timeout=3600)
    return HttpResponse(html)






























































































