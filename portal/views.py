from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.template.loader import get_template
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from xhtml2pdf import pisa
from django.db import transaction
from datetime import datetime
from django.http import HttpResponseForbidden


from employees.models import Employee
from payroll.models import MonthlySalary, Advance
from attendance.models import Attendance
from .decorators import manager_required

# =========================================
# 👷 WORKER PORTAL VIEWS
# =========================================

def portal_login(request):
    # 1. If already logged in, redirect based on role
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
            return redirect('manager_dashboard')
        return redirect('worker_dashboard')

    if request.method == "POST":
        # We accept 'login_id' which can be EITHER a Username OR a Phone Number
        login_id = request.POST.get('login_id') 
        password = request.POST.get('password')
        
        user = None

        # STRATEGY A: Try as Manager/Admin (Username Search)
        user = authenticate(request, username=login_id, password=password)

        # STRATEGY B: Try as Worker (Phone Number Search)
        if user is None:
            try:
                # Find the employee with this phone number
                employee = Employee.objects.get(
                    phone_number=login_id, 
                    is_active=True
                )
                # Authenticate using the linked User account
                user = authenticate(
                    request, 
                    username=employee.user.username, 
                    password=password
                )
            except Employee.DoesNotExist:
                pass

        # FINAL CHECK
        if user is not None:
            if user.is_active:
                login(request, user)
                # Redirect based on who they are
                if user.is_superuser or user.groups.filter(name='Manager').exists():
                    messages.success(request, "Welcome back, Manager.")
                    return redirect('manager_dashboard')
                else:
                    return redirect('worker_dashboard')
            else:
                messages.error(request, "Account is disabled.")
        else:
            messages.error(request, "Invalid ID or Password.")

    return render(request, 'portal/login.html')

@login_required(login_url='portal_login')
def worker_dashboard(request):
    try:
        employee = request.user.employee
        if not employee.is_active:
             raise Employee.DoesNotExist
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')

    salaries = MonthlySalary.objects.filter(employee=employee).order_by('-month')
    return render(request, 'portal/dashboard.html', {'employee': employee, 'salaries': salaries})

def worker_logout(request):
    logout(request)
    return redirect('portal_login')

@login_required
def worker_profile(request):
    # FIX: Defensive check for missing employee profile
    try:
        employee = request.user.employee
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')
        
    return render(request, 'portal/profile.html', {'employee': employee})

@login_required
def worker_attendance(request):
    # FIX: Defensive check for missing employee profile
    try:
        employee = request.user.employee
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')
        
    # Get last 30 days of attendance
    logs = Attendance.objects.filter(employee=employee).order_by('-date')[:30]
    return render(request, 'portal/attendance.html', {'logs': logs})

@login_required
def download_payslip(request, salary_id):
    salary = get_object_or_404(
        MonthlySalary.objects.select_related('employee'), 
        id=salary_id
    )

    # FIX: Strict RBAC - Only Superuser or Manager Group can bypass ownership
    is_manager = request.user.groups.filter(name='Manager').exists()
    
    if request.user.is_superuser or is_manager:
        pass  # Access granted
    elif hasattr(request.user, 'employee'):
        # Check 1: Ownership
        if salary.employee != request.user.employee:
            raise PermissionDenied("⛔ You are not authorized to view this payslip.")
        
        # Check 2: Status
        if not salary.is_paid:
            raise PermissionDenied("⏳ Payslip not available until salary is paid.")
    else:
        raise PermissionDenied("Unauthorized access.")

    # Generate PDF
    template_path = 'payroll/payslip_pdf.html'
    context = {'salary': salary}
    response = HttpResponse(content_type='application/pdf')
    filename = f"Payslip_{salary.employee.name}_{salary.month.strftime('%b_%Y')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    
    return response

# =========================================
# 📊 MANAGER PORTAL VIEWS
# =========================================
from django.utils import timezone
from datetime import datetime

@manager_required
def manager_dashboard(request):
    """
    The 'Cockpit' View for Managers.
    Calculates Financials (Gross vs Net), Workforce stats, and Liability.
    """

    context = {}  # always initialize once

    current_time = timezone.now()
    today = current_time.date()
    selected_month = today.replace(day=1)

    # needed for navigation (salary list, summary)
    context["selected_month"] = selected_month.strftime("%Y-%m")
    
    # check if payroll exists for selected month (for dashboard navigation)
    month_date = datetime.strptime(
        context["selected_month"], "%Y-%m"
    ).date().replace(day=1)

    payroll_exists = MonthlySalary.objects.filter(
        month=month_date
    ).exists()

    context["payroll_exists"] = payroll_exists


    # 1. WORKFORCE METRICS
    total_workers = Employee.objects.filter(is_active=True).count()

    new_joinees = Employee.objects.filter(
        join_date__year=current_time.year,
        join_date__month=current_time.month,
        is_active=True
    ).count()

    # 2. FINANCIAL METRICS (current month)
    financials = MonthlySalary.objects.filter(
        month=selected_month
    ).aggregate(
        total_gross=Coalesce(Sum("gross_pay"), Decimal("0.00")),
        total_net=Coalesce(Sum("net_pay"), Decimal("0.00")),
        total_paid=Coalesce(
            Sum("net_pay", filter=Q(is_paid=True)), Decimal("0.00")
        ),
        recovered=Coalesce(Sum("advance_deducted"), Decimal("0.00")),
    )

    # 3. LIABILITY
    outstanding_liability = financials["total_net"] - financials["total_paid"]

    # 4. ADVANCES (issued this month)
    advances_given = Advance.objects.filter(
        issued_date__year=current_time.year,
        issued_date__month=current_time.month,
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    # update context (never overwrite)
    context.update({
        "current_month": current_time,
        "total_workers": total_workers,
        "new_joinees": new_joinees,
        "financials": financials,
        "outstanding_liability": outstanding_liability,
        "advances_given": advances_given,
    })

    return render(request, "portal/manager_dashboard.html", context)


@manager_required
def bulk_attendance(request):
    """
    Bulk Attendance Interface.
    Allows marking 100+ workers in one go.
    """
    # 1. Get Date from URL (or default to Today)
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    # 2. Handle SAVE (POST)
    if request.method == "POST":
        post_date_str = request.POST.get('attendance_date')
        selected_date = datetime.strptime(post_date_str, '%Y-%m-%d').date()
        
        try:
            with transaction.atomic():
                # Loop through POST data to find status keys
                for key, value in request.POST.items():
                    if key.startswith('status_'):
                        # key format: status_101 (where 101 is employee ID)
                        emp_id = key.split('_')[1]
                        
                        status = value
                        overtime = request.POST.get(f'overtime_{emp_id}', 0)
                        
                        # Validate Overtime is a number
                        if not overtime: overtime = 0
                        
                        # Update or Create
                        Attendance.objects.update_or_create(
                            employee_id=emp_id,
                            date=selected_date,
                            defaults={
                                'status': status,
                                'overtime_hours': overtime,
                                
                            }
                        )
                
            # COUNT STATUSES
            present = 0
            absent = 0
            half_day = 0
            
            for key, value in request.POST.items():
                if key.startswith('status_'):
                    if value == 'P':
                        present += 1
                    elif value == 'A':
                        absent += 1
                    elif value == 'H':
                        half_day += 1
            
            # SUCCESS MESSAGE
            messages.success(
                request,
                f"✓ Attendance saved for {selected_date} | "
                f"Present: {present} | Half Day: {half_day} | Absent: {absent}"
            )
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    # 3. Handle VIEW (GET)
    # Fetch all active workers
    workers = Employee.objects.filter(is_active=True).order_by('id')
    
    # Pre-fetch existing attendance to fill the form
    existing_attendance = Attendance.objects.filter(date=selected_date)
    attendance_map = {att.employee_id: att for att in existing_attendance}

    worker_list = []
    for worker in workers:
        att = attendance_map.get(worker.id)
        worker_list.append({
            'employee': worker,
            'status': att.status if att else 'Present', # Default to Present
            'overtime': att.overtime_hours if att else 0,
        })

    context = {
        'selected_date': selected_date,
        'worker_list': worker_list,
        'today': timezone.now().date(),
    }
    
    return render(request, 'portal/bulk_attendance.html', context)


from payroll.services import generate_monthly_salary, SalaryAlreadyGeneratedError

@manager_required
def run_payroll(request):
    """
    Manager Payroll Orchestrator
    Uses the existing payroll engine safely.
    """
    today = timezone.now().date()

    if request.method == "POST":
        print("🚀 RUN PAYROLL POST HIT")
        try:
            selected_month = datetime.strptime(
                request.POST.get('payroll_month'),
                '%Y-%m'
            ).date().replace(day=1)
            
        except (ValueError, TypeError):
            messages.error(request, "Invalid month selected.")
            return redirect('manager_dashboard')
        print(f"📅 Payroll Month Selected: {selected_month}")
        

        employees = Employee.objects.filter(is_active=True)
        print(f"👥 Active Employees: {employees.count()}")

        created = 0
        skipped = 0
        failed = 0

        with transaction.atomic():
            for employee in employees:
                print(f"👷 Processing employee: {employee.name}")
                try:
                    salary = generate_monthly_salary(employee, selected_month)

                    if salary is None:
                        skipped += 1
                        print(f"⏭️ Skipped {employee.name} (no payable data)")
                    else:
                        created += 1
                        print(f"✅ Salary created for {employee.name}")

                except SalaryAlreadyGeneratedError:
                    skipped += 1
                    print("⚠️ Already generated")


                except Exception as e:
                    failed += 1
                    print(f"❌ Failed: {e}")

        messages.success(
            request,
            f"Payroll for {selected_month.strftime('%B %Y')} completed | "
            f"Created: {created}, Skipped: {skipped}, Failed: {failed}"
        )
        return redirect(
            f"/payroll/manager/payroll/summary/?month={selected_month.strftime('%Y-%m')}"
)


    return render(request, 'portal/run_payroll.html', {'today': today})




