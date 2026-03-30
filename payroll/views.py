from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import csv
from .models import MonthlySalary
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from decimal import Decimal
from datetime import datetime, date, timedelta

from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.http import Http404

from django.shortcuts import redirect
from django.contrib import messages

from payroll.services import generate_monthly_salary, SalaryAlreadyGeneratedError

from portal.decorators import manager_required
from django.core.exceptions import ValidationError
from employees.models import Employee
from .services import issue_advance
from django.utils import timezone
from django.views.decorators.http import require_POST


@login_required
def download_payslip(request, salary_id):
    # --- IMPROVEMENT 2: PERFORMANCE ---
    # Fetch salary AND employee data in 1 query (saves DB hits)
    salary = get_object_or_404(
        MonthlySalary.objects.select_related('employee'), 
        id=salary_id
    )

    # --- SECURITY & BUSINESS LOGIC CHECKS ---
    
    # Case A: Admin/Superuser (Allow access to everything)
    if request.user.is_superuser or request.user.is_staff:
        pass 
    
    # Case B: Worker (Strict Checks)
    elif hasattr(request.user, 'employee'):
        # Check 1: Ownership (Prevent ID guessing)
        if salary.employee != request.user.employee:
            raise PermissionDenied("⛔ You are not authorized to view this payslip.")
        
        # --- IMPROVEMENT 1: BUSINESS LOGIC ---
        # Check 2: Status (Prevent early access)
        if not salary.is_paid:
            raise PermissionDenied("⏳ Payslip not available until salary is paid.")
            
    # Case C: Random User (Block)
    else:
        raise PermissionDenied("Unauthorized access.")
    # -------------------------------------

    # Generate PDF (Standard Logic)
    template_path = 'payroll/payslip_pdf.html'
    context = {'salary': salary}
    response = HttpResponse(content_type='application/pdf')
    # Use clean filename
    filename = f"Payslip_{salary.employee.name}_{salary.month.strftime('%b_%Y')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    
    return response

@manager_required
def payroll_batch_summary(request, viewing_as_owner=False):
    """
    Payroll Batch Summary - Shows current or previous month payroll
    
    LOGIC:
    1. If month param provided, use it
    2. Else, try current month payroll
    3. If current month has no payroll, fallback to previous month
    4. Show month selector to allow switching between months
    
    This ensures contractors can always see payroll status even if current month isn't generated yet.
    """
    today = date.today()
    current_month_str = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    
    # STEP 1: Determine which month to display
    selected_month = request.GET.get("month")
    
    if not selected_month:
        # Try current month first
        month_to_check = current_month_str
        
        # Check if current month has payroll
        check_date = datetime.strptime(month_to_check, "%Y-%m").date()
        if not MonthlySalary.objects.filter(month__year=check_date.year, month__month=check_date.month).exists():
            # Fall back to previous month
            selected_month = prev_month
        else:
            selected_month = month_to_check
    
    # Parse selected month
    try:
        month_date = datetime.strptime(selected_month, "%Y-%m").date()
    except ValueError:
        raise Http404("Invalid month format. Expected YYYY-MM")
    
    # STEP 2: Get payroll data for selected month
    salaries_qs = MonthlySalary.objects.filter(
        month__year=month_date.year,
        month__month=month_date.month
    )
    
    batch_generated_at = salaries_qs.order_by("generated_at").values_list(
        "generated_at", flat=True
    ).first()
    
    # STEP 3: Get available months for dropdown (only up to current month)
    # Find all months that have payroll data, but exclude future months
    all_months_raw = MonthlySalary.objects.values_list("month", flat=True).distinct().order_by("-month")
    
    # Filter to only include months up to and including current month
    current_date = date.today()
    available_months_list = []
    for m in all_months_raw:
        # Only include if month is <= current month
        if m.year < current_date.year or (m.year == current_date.year and m.month <= current_date.month):
            month_str = m.strftime("%Y-%m")
            month_display_name = m.strftime("%B %Y")
            available_months_list.append({"value": month_str, "display": month_display_name})
            # Limit to last 12 months
            if len(available_months_list) >= 12:
                break
    
    available_months = available_months_list
    
    if not salaries_qs.exists():
        # No payroll for selected month
        context = {
            "selected_month": selected_month,
            "available_months": available_months,
            "current_month_str": current_month_str,
            "prev_month_str": prev_month,
            "month_display": datetime.strptime(selected_month, "%Y-%m").strftime("%B %Y"),
            "has_payroll": False,
        }
        return render(
            request,
            "payroll/payroll_batch_summary.html",
            context
        )
    
    # STEP 4: Aggregate payroll data
    aggregates = salaries_qs.aggregate(
        total_employees=Count("id"),
        total_gross=Coalesce(Sum("gross_pay"), Decimal("0.00")),
        total_advance_deducted=Coalesce(Sum("advance_deducted"), Decimal("0.00")),
        total_net=Coalesce(Sum("net_pay"), Decimal("0.00")),
        paid_count=Count("id", filter=Q(is_paid=True)),
        unpaid_count=Count("id", filter=Q(is_paid=False)),
    )
    
    unpaid_liability = salaries_qs.filter(is_paid=False).aggregate(
        liability=Coalesce(Sum("net_pay"), Decimal("0.00"))
    )["liability"]
    
    # STEP 5: Build context with month selector data
    context = {
        "selected_month": selected_month,
        "month_display": datetime.strptime(selected_month, "%Y-%m").strftime("%B %Y"),  # "March 2026"
        "available_months": available_months,
        "current_month_str": current_month_str,
        "prev_month_str": prev_month,
        "total_employees": aggregates["total_employees"],
        "paid_count": aggregates["paid_count"],
        "unpaid_count": aggregates["unpaid_count"],
        "total_gross": aggregates["total_gross"],
        "total_advance_deducted": aggregates["total_advance_deducted"],
        "total_net": aggregates["total_net"],
        "total_liability": unpaid_liability,
        "generated_at": batch_generated_at,
        "has_payroll": True,
    }
    
    return render(
        request,
        "payroll/payroll_batch_summary.html",
        context
    )


@manager_required
def salary_list_view(request):
    selected_month = request.GET.get("month")

    if not selected_month:
        # Default to current month
        today = timezone.now().date()
        month_date = today.replace(day=1)
        selected_month = month_date.strftime("%Y-%m")

    try:
        month_date = datetime.strptime(selected_month, "%Y-%m").date()
    except ValueError:
        raise Http404("Invalid month format")

    employees = Employee.objects.all()

    # Salaries already generated for this month
    salaries = MonthlySalary.objects.filter(
        month__year=month_date.year,
        month__month=month_date.month
    ).select_related("employee")

    # Map: employee_id -> salary
    salary_map = {s.employee_id: s for s in salaries}

    rows = []
    for employee in employees:
        rows.append({
            "employee": employee,
            "salary": salary_map.get(employee.id),  # None if not generated
        })

    context = {
        "selected_month": selected_month,
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

    except Exception as e:
        messages.error(
            request,
            f"❌ Failed to generate salary for {employee.name}: {e}"
        )

    return redirect(
        f"/payroll/manager/payroll/salaries/?month={selected_month}"
    )

@manager_required
@require_POST
def mark_salary_paid(request):
    salary_id = request.POST.get("salary_id")
    selected_month = request.POST.get("month")

    if not salary_id or not selected_month:
        raise Http404("Invalid request")

    salary = get_object_or_404(MonthlySalary, id=salary_id)

    # Safety check: prevent double marking
    if salary.is_paid:
        messages.warning(
            request,
            f"⚠️ Salary already marked as paid for {salary.employee.name}"
        )
        return redirect(
            f"/payroll/manager/payroll/salaries/?month={selected_month}"
        )

    salary.is_paid = True
    salary.paid_on = timezone.now()
    salary.save(update_fields=["is_paid", "paid_on"])

    timestamp = salary.paid_on.strftime("%d %b %Y %H:%M")

    messages.success(
        request,
        f"✅ Salary marked as PAID for {salary.employee.name} "
        f"at {timestamp}"
    )

    return redirect(
        f"/payroll/manager/payroll/salaries/?month={selected_month}"
    )

@manager_required
def export_salary_list_csv(request):
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
    writer.writerow([
        "Employee Name",
        "Gross Pay",
        "Advance Deducted",
        "Net Pay",
        "Status",
        "Paid On"
    ])

    for salary in salaries:
        writer.writerow([
            salary.employee.name,
            salary.gross_pay,
            salary.advance_deducted,
            salary.net_pay,
            "Paid" if salary.is_paid else "Unpaid",
            salary.paid_on.strftime("%d-%b-%Y %H:%M") if salary.paid_on else ""
        ])

    return response

# ==========================================================
# ISSUE ADVANCE VIEW
# ==========================================================
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

    # Only active employees can receive advances
    employees = Employee.objects.filter(is_active=True)

    if request.method == "POST":

        employee_id = request.POST.get("employee")
        amount = request.POST.get("amount")
        issued_date = request.POST.get("issued_date")

        try:
            employee = Employee.objects.get(id=employee_id)

            # Delegate financial responsibility to service layer
            issue_advance(employee, amount, issued_date)

            return render(
                request,
                "payroll/issue_advance.html",
                {
                    "employees": employees,
                    "success": "Advance issued successfully."
                }
            )

        except ValidationError as e:
            return render(
                request,
                "payroll/issue_advance.html",
                {
                    "employees": employees,
                    "error": str(e)
                }
            )

    # GET Request: Render empty form
    return render(
        request,
        "payroll/issue_advance.html",
        {
            "employees": employees,
            "today": timezone.now().date()
        }
    )



    