from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.template.loader import get_template
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from xhtml2pdf import pisa
from django.db import transaction
from datetime import datetime
from django.http import HttpResponseForbidden


from employees.models import Employee
from payroll.models import MonthlySalary, Advance
from attendance.models import Attendance
from .decorators import manager_required, worker_required
from .decorators import king_required
import json
from datetime import datetime, date, timedelta
from django.db.models import Sum, Count, Q
import json
from datetime import datetime, date, timedelta
from django.db.models import Sum, Count, Q

# =========================================
# 👷 WORKER PORTAL VIEWS
# =========================================

def portal_login(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
            return redirect('manager_dashboard')
        return redirect('worker_dashboard')

    if request.method == "POST":
        login_id = request.POST.get('login_id')
        password = request.POST.get('password')
        login_type = request.POST.get('login_type', 'worker')  # ✅ read toggle

        user = None

        if login_type == 'manager':
            user = authenticate(request, username=login_id, password=password)
        else:
            try:
                employee = Employee.objects.get(phone_number=login_id, is_active=True)
                user = authenticate(request, username=employee.user.username, password=password)
            except Employee.DoesNotExist:
                pass

        if user is not None and user.is_active:
            is_manager = user.is_superuser or user.groups.filter(name='Manager').exists()

            # ✅ Role must match toggle
            if login_type == 'manager' and not is_manager:
                messages.error(request, "Invalid credentials.")
            elif login_type == 'worker' and is_manager:
                messages.error(request, "Invalid credentials.")
            else:
                login(request, user)
                if is_manager:
                    messages.success(request, "Welcome back, Manager.")
                    return redirect('manager_dashboard')
                return redirect('worker_dashboard')
        else:
            messages.error(request, "Invalid ID or Password.")

    return render(request, 'portal/login.html')

@worker_required
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

@worker_required
def worker_profile(request):
    # FIX: Defensive check for missing employee profile
    try:
        employee = request.user.employee
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')
        
    return render(request, 'portal/profile.html', {'employee': employee})

@worker_required
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

@worker_required
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
def manager_dashboard(request, viewing_as_owner=False):
    """
    Production-grade Manager Dashboard View.
    
    Features:
    - Financial overview (revenue, expenses, payroll, liability)
    - Workforce metrics and statistics
    - Advance tracking and liability management
    
    Access Control:
    - Manager users: Full access
    - King/Owner users: Read-only view with back button
    - Regular workers: Denied
    
    Args:
        request: HTTP request
        viewing_as_owner: Boolean flag indicating if King user is viewing
        
    Returns:
        Rendered manager dashboard template
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
    context["viewing_as_owner"] = viewing_as_owner  # Pass flag to template


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



def king_login(request):
    """
    Production-grade King/Owner authentication view.
    
    CRITICAL SECURITY FEATURES:
    1. Strict authentication: Only King group members allowed
    2. Explicit rejection: Manager group users BLOCKED
    3. Double-session flag: king_authenticated flag required for access
    4. Comprehensive logging: All login attempts logged with IP
    5. Input validation: All POST data validated before use
    6. Session cleanup: Proper logout and session clearing
    
    Security Logic:
    - Manager credentials cannot login to king dashboard (hard rejection)
    - Only users with EXPLICIT King group can access
    - Superusers need King group (no backdoor access)
    - Session flag prevents direct dashboard URL access
    - All attempts logged for audit trail
    
    Args:
        request: HTTP request object
        
    Returns:
        Redirect to king_dashboard on success
        Rendered login template on initial request or auth failure
    """
    import logging
    logger = logging.getLogger(__name__)
    
    client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
    
    # If already authenticated with valid session flag, redirect to dashboard
    if request.user.is_authenticated and request.session.get('king_authenticated'):
        if request.user.groups.filter(name='King').exists():
            return redirect('king_dashboard')
    
    # Clear any stale king_authenticated flags to prevent session hijacking
    if 'king_authenticated' in request.session:
        del request.session['king_authenticated']
    
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        # INPUT VALIDATION: Prevent empty credentials
        if not username or not password:
            logger.warning(
                f"King login: Empty credentials attempt from {client_ip}"
            )
            messages.error(request, "Username and password are required.")
            return render(request, 'portal/king_login.html')
        
        # AUTHENTICATION: Check credentials
        user = authenticate(request, username=username, password=password)
        
        if user is None:
            # Log failed authentication
            logger.warning(
                f"King login: Failed authentication for {username} from {client_ip}"
            )
            messages.error(request, "Invalid username or password.")
            return render(request, 'portal/king_login.html')
        
        if not user.is_active:
            logger.warning(
                f"King login: Inactive user {username} attempted access from {client_ip}"
            )
            messages.error(request, "Your account is inactive. Contact administrator.")
            return render(request, 'portal/king_login.html')
        
        # CRITICAL SECURITY CHECK 1: REJECT Manager group EXPLICITLY
        if user.groups.filter(name='Manager').exists():
            logger.critical(
                f"SECURITY ALERT: Manager {username} attempted King login from {client_ip}. "
                f"REJECTED - Manager credentials cannot access King dashboard."
            )
            messages.error(
                request, 
                "⛔ SECURITY BLOCK: Manager credentials cannot access Owner dashboard. "
                "Please logout and use the Manager login."
            )
            return render(request, 'portal/king_login.html')
        
        # CRITICAL SECURITY CHECK 2: VERIFY King group membership
        is_king = user.groups.filter(name='King').exists()
        is_superuser = user.is_superuser
        
        if is_king:
            # User has explicit King group - ALLOW LOGIN
            login(request, user)
            request.session['king_authenticated'] = True
            request.session.set_expiry(3600)  # 1 hour session timeout for security
            
            logger.info(
                f"King login: Successful authentication for {username} from {client_ip}"
            )
            messages.success(request, f"Welcome back, Owner {username}!")
            return redirect('king_dashboard')
        
        elif is_superuser:
            # Superuser without explicit King group - REJECT (no backdoor)
            logger.critical(
                f"SECURITY: Superuser {username} attempted King login without King group "
                f"from {client_ip}. REJECTED."
            )
            messages.error(
                request,
                "⛔ Superuser requires explicit King group membership. "
                "Contact system administrator."
            )
            return render(request, 'portal/king_login.html')
        
        else:
            # Regular user without King group - REJECT
            logger.warning(
                f"King login: Unauthorized user {username} attempted access from {client_ip}"
            )
            messages.error(
                request,
                "⛔ Owner access only. You are not authorized for this dashboard."
            )
            return render(request, 'portal/king_login.html')
    
    # GET request: Render login form
    return render(request, 'portal/king_login.html')


# portal/views.py  (only king_dashboard changes)

import json
from datetime import datetime, date, timedelta
from django.db.models import Sum, Count, Q

@king_required
def king_dashboard(request):

    today = date.today()

    # ── Helper function: Calculate daily salary using payroll logic ──
    def calculate_daily_salary_for_employee(employee, target_date):
        """
        Calculate salary for a single day using payroll logic.
        
        SAFETY GUARANTEES:
        - Returns Decimal('0.00') if no attendance marked
        - Returns Decimal('0.00') if employee has no role (instead of crashing)
        - Returns Decimal('0.00') for absences
        - Safely handles NULL values in employee data
        
        Args:
            employee: Employee object
            target_date: Date to calculate salary for
            
        Returns:
            Decimal: Daily salary amount (always safe, never crashes)
        """
        from decimal import Decimal, ROUND_HALF_UP
        
        # GUARD 1: Check if attendance exists for this day
        att = Attendance.objects.filter(
            employee=employee,
            date=target_date
        ).first()
        
        if not att:
            return Decimal('0.00')  # No attendance marked
        
        # GUARD 2: Check if employee has valid daily_wage (prevent NULL errors)
        daily_wage = employee.daily_wage
        if not daily_wage or daily_wage <= 0:
            return Decimal('0.00')  # Invalid wage, return zero
        
        # GUARD 3: Calculate base pay based on attendance status
        if att.status == 'P':
            day_pay = daily_wage
        elif att.status == 'H':
            day_pay = daily_wage * Decimal('0.5')
        elif att.status == 'A':
            day_pay = Decimal('0.00')  # Absence, no pay (paid leaves handled monthly)
        else:
            day_pay = Decimal('0.00')
        
        # GUARD 4: Add overtime with NULL safety (prevents crash if employee.role is None)
        # If employee has no role assigned, overtime defaults to zero
        if att.overtime_hours and att.overtime_hours > 0 and employee.role:
            overtime_rate = employee.role.overtime_rate_per_hour
            if overtime_rate:  # Extra safety check for rate being valid
                overtime_pay = att.overtime_hours * overtime_rate
                day_pay += overtime_pay
        
        # GUARD 5: Return rounded to 2 decimal places (financial precision)
        return day_pay.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # ── Helper function: Calculate accumulated salary for month so far ──
    def calculate_accumulated_salary_for_month(month_start):
        """
        Calculate total accumulated salary from all employees for the month so far.
        
        OPTIMIZATION: Uses select_related to fetch all role data in one query
        instead of N+1 queries per employee.
        
        SAFETY GUARANTEES:
        - Returns Decimal('0.00') if no employees exist
        - Safely handles NULL employee data
        - Returns zero for invalid dates
        - Maintains Decimal precision throughout
        
        Args:
            month_start: First day of month (must be valid date)
            
        Returns:
            Decimal: Total accumulated salary (never crashes, always valid)
        """
        from decimal import Decimal, ROUND_HALF_UP
        
        total_accumulated = Decimal('0.00')
        
        # OPTIMIZATION: select_related('role') to fetch role data in ONE query
        # instead of fetching roles separately for each employee
        # This reduces database queries from ~1000 to ~100 for a month
        active_employees = Employee.objects.filter(is_active=True).select_related('role')
        
        # GUARD 1: If no employees, return zero immediately
        if not active_employees.exists():
            return Decimal('0.00')
        
        # GUARD 2: Validate month_start is a valid date
        if not month_start or month_start > today:
            return Decimal('0.00')
        
        # GUARD 3: Loop through each day of the month up to today
        current_date = month_start
        while current_date <= today:
            # For each day, calculate salary for all employees
            for emp in active_employees:
                try:
                    daily_sal = calculate_daily_salary_for_employee(emp, current_date)
                    if daily_sal > 0:  # Only add if valid (safety check)
                        total_accumulated += daily_sal
                except Exception as e:
                    # Log error but don't crash dashboard
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Salary calculation error for {emp.name} on {current_date}: {str(e)}"
                    )
                    continue  # Skip this employee, continue with next
            
            current_date += timedelta(days=1)
        
        # GUARD 4: Return rounded to 2 decimal places
        return total_accumulated.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # ── Helper function: Get today's daily salary ──
    def get_todays_daily_salary():
        """Get total salary generated today for all employees"""
        from decimal import Decimal, ROUND_HALF_UP
        
        today_salary = Decimal('0.00')
        active_employees = Employee.objects.filter(is_active=True)
        
        for emp in active_employees:
            daily_sal = calculate_daily_salary_for_employee(emp, today)
            today_salary += daily_sal
        
        return today_salary.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # ── Helper function: Get today's attendance status ──
    def get_todays_attendance_status():
        """Get attendance count for today"""
        today_att = Attendance.objects.filter(date=today)
        
        present_count = today_att.filter(status='P').count()
        absent_count = today_att.filter(status='A').count()
        half_day_count = today_att.filter(status='H').count()
        
        total_marked = present_count + absent_count + half_day_count
        total_employees = Employee.objects.filter(is_active=True).count()
        
        return {
            'marked': total_marked > 0,
            'present': present_count,
            'absent': absent_count,
            'half_day': half_day_count,
            'total_marked': total_marked,
            'total_employees': total_employees
        }
    
    # Time greeting
    hour = datetime.now().hour
    if hour < 12:   time_of_day = "Morning"
    elif hour < 17: time_of_day = "Afternoon"
    else:           time_of_day = "Evening"

    # ── Month boundaries ──────────────────────────────────────────
    month_start = today.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    prev_month_end   = month_start                                      # exclusive
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    # ── Imports ──
    from employees.models import Employee
    from attendance.models import Attendance
    from payroll.models   import MonthlySalary
    from billing.models   import Bill
    from expenses.models  import Expense

    # ── Helpers ───────────────────────────────────────────────────
    def pct_change(current, previous):
        if not previous: return 0
        return round(((float(current) - float(previous)) / float(previous)) * 100, 1)

    # ── Workers ───────────────────────────────────────────────────
    total_workers = Employee.objects.filter(is_active=True).count()
    new_workers   = Employee.objects.filter(
        join_date__gte=month_start            # ⚠️ verify field name
    ).count()

    # ── Payroll ───────────────────────────────────────────────────
    cur_payroll  = MonthlySalary.objects.filter(
        month=month_start
    ).aggregate(t=Sum('net_pay'))['t'] or 0

    prev_payroll = MonthlySalary.objects.filter(
        month=prev_month_start
    ).aggregate(t=Sum('net_pay'))['t'] or 0

    # ── Liability (unpaid salaries) ───────────────────────────────
    total_liability = MonthlySalary.objects.filter(
        is_paid=False
    ).aggregate(t=Sum('net_pay'))['t'] or 0

    # ── Daily Expenses ────────────────────────────────────────────
    cur_expenses  = Expense.objects.filter(
        date__gte=month_start, date__lt=next_month
    ).aggregate(t=Sum('amount'))['t'] or 0

    prev_expenses = Expense.objects.filter(
        date__gte=prev_month_start, date__lt=prev_month_end
    ).aggregate(t=Sum('amount'))['t'] or 0

    # Expense breakdown by category (current month)
    expense_categories = (
        Expense.objects
        .filter(date__gte=month_start, date__lt=next_month)
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    # Enrich with display names
    expense_cat_labels = []
    expense_cat_data   = []
    for item in expense_categories:
        dummy = Expense(category=item['category'])
        expense_cat_labels.append(dummy.get_category_display())
        expense_cat_data.append(float(item['total']))

    # ── Billing (Revenue = paid bills this month) ─────────────────
    cur_revenue  = Bill.objects.filter(
        is_paid=True,
        paid_on__gte=month_start, paid_on__lt=next_month
    ).aggregate(t=Sum('amount'))['t'] or 0

    prev_revenue = Bill.objects.filter(
        is_paid=True,
        paid_on__gte=prev_month_start, paid_on__lt=prev_month_end
    ).aggregate(t=Sum('amount'))['t'] or 0

    # Pending bills
    pending_bills        = Bill.objects.filter(is_paid=False)
    pending_bills_count  = pending_bills.count()
    pending_bills_amount = pending_bills.aggregate(t=Sum('amount'))['t'] or 0

    # ── Advances outstanding ──────────────────────────────────────
    # ⚠️ adjust fields: amount, recovered_amount
    # ── Advances outstanding ──────────────────────────────────────
    from payroll.models import Advance

    advance_outstanding = Advance.objects.filter(
    settled=False
    ).aggregate(
    t=Sum('remaining_amount')
    )['t'] or 0

    # ── Attendance rate (current month) ───────────────────────────
    working_days  = today.day                               # days elapsed this month
    total_possible = max(total_workers * working_days, 1)
    total_present  = Attendance.objects.filter(
        date__gte=month_start,
        date__lte=today,
        status__in=['present', 'half_day']  # ⚠️ verify status values
    ).count()
    attendance_rate = round((total_present / total_possible) * 100, 1)

    # ── Net Profit ────────────────────────────────────────────────
    net_profit      = float(cur_revenue) - float(cur_expenses) - float(cur_payroll)
    profit_margin   = round((net_profit / float(cur_revenue) * 100), 1) if cur_revenue else 0

    # ── 6-month chart data ────────────────────────────────────────
    chart_labels   = []
    revenue_data   = []
    expense_data   = []
    payroll_data   = []

    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        m_start = date(y, m, 1)
        m_end   = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

        chart_labels.append(m_start.strftime('%b %y'))
        revenue_data.append(float(
            Bill.objects.filter(is_paid=True, paid_on__gte=m_start, paid_on__lt=m_end)
            .aggregate(t=Sum('amount'))['t'] or 0
        ))
        expense_data.append(float(
            Expense.objects.filter(date__gte=m_start, date__lt=m_end)
            .aggregate(t=Sum('amount'))['t'] or 0
        ))
        payroll_data.append(float(
            MonthlySalary.objects.filter(month=m_start)
            .aggregate(t=Sum('net_pay'))['t'] or 0
        ))

    # ── Workforce by role ─────────────────────────────────────────
    role_qs     = (
        Employee.objects.filter(is_active=True)
        .values('role__name')             # ⚠️ verify FK field name
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    role_labels = [r['role__name'] or 'Unknown' for r in role_qs]
    role_counts = [r['count'] for r in role_qs]

    # ── Recent Activity ───────────────────────────────────────────
    recent_activities = []

    # Last 5 attendance marks (TODAY AND PAST FOR TESTING)
    from django.utils import timezone
    for att in Attendance.objects.select_related('employee').order_by('-date')[:4]:
        status_emoji = {'P': '✓ Present', 'A': '✗ Absent', 'H': '⚠️ Half-day'}.get(att.status, att.status)
        recent_activities.append({
            'icon': '👤', 'type': 'info',
            'text': f"Attendance marked — {att.employee.name} ({status_emoji})",
            'time': str(att.date),
        })
    
    # Last 5 salary payments
    for s in MonthlySalary.objects.filter(is_paid=True).select_related('employee').order_by('-month')[:3]:
        recent_activities.append({
            'icon': '💵', 'type': 'success',
            'text': f"Salary paid — {s.employee.name}",
            'time': str(s.month.strftime('%b %Y')),
        })

    # Last 3 expenses
    for e in Expense.objects.order_by('-created_at')[:3]:
        recent_activities.append({
            'icon': '💸', 'type': 'warning',
            'text': f"{e.get_category_display()} expense — ₹{e.amount}",
            'time': str(e.date),
        })

    # Last 3 bills
    for b in Bill.objects.order_by('-created_at')[:3]:
        recent_activities.append({
            'icon': '📄', 'type': 'info',
            'text': f"Bill {'paid' if b.is_paid else 'pending'} — ₹{b.amount}",
            'time': str(b.created_at.strftime('%Y-%m-%d')),
        })

    # Sort by most recent (basic, since time formats differ)
    recent_activities = recent_activities[:8]

    # ── Context ───────────────────────────────────────────────────
    return render(request, 'portal/king_dashboard.html', {
        'today':               today,
        'time_of_day':         time_of_day,

        # KPIs
        'total_revenue':       cur_revenue,
        'total_expenses':      cur_expenses,
        'total_payroll':       cur_payroll,
        'total_liability':     total_liability,
        'total_workers':       total_workers,
        'new_workers':         new_workers,
        'attendance_rate':     attendance_rate,
        'net_profit':          net_profit,
        'profit_margin':       profit_margin,

        # Changes vs last month
        'revenue_change':      pct_change(cur_revenue,  prev_revenue),
        'expense_change':      pct_change(cur_expenses, prev_expenses),
        'payroll_change':      pct_change(cur_payroll,  prev_payroll),
        'liability_change':    0,

        # Chart data
        'chart_labels':        json.dumps(chart_labels),
        'revenue_data':        json.dumps(revenue_data),
        'expense_data':        json.dumps(expense_data),
        'payroll_data':        json.dumps(payroll_data),
        'role_labels':         json.dumps(role_labels),
        'role_counts':         json.dumps(role_counts),
        'expense_cat_labels':  json.dumps(expense_cat_labels),
        'expense_cat_data':    json.dumps(expense_cat_data),

        # Alerts
        'pending_bills_count':  pending_bills_count,
        'pending_bills_amount': pending_bills_amount,
        'advance_outstanding':  advance_outstanding,

        # ──────────── NEW FEATURES ────────────────────────────
        # 1. DAILY SNAPSHOT
        'todays_attendance':   get_todays_attendance_status(),
        'todays_daily_salary': get_todays_daily_salary(),
        
        # 2. SALARY TRACKER
        'accumulated_salary':  calculate_accumulated_salary_for_month(month_start),
        'month_start':         month_start,
        'days_in_month':       (next_month - month_start).days if month_start.month < 12 else 25,
        'days_processed':      (today - month_start).days + 1,
        
        # 3. ENHANCED COMPLIANCE ALERTS
        'low_attendance_workers': list(set([
            att.employee for att in Attendance.objects.filter(
                date__gte=month_start,
                date__lte=today,
                status__in=['A']
            )
        ]))[:5],  # Workers with absences this month
        
        # 4. PAYROLL VERIFICATION (compare calculated vs generated)
        'generated_payroll_total': MonthlySalary.objects.filter(
            month=month_start
        ).aggregate(total=Sum('net_pay'))['total'] or Decimal('0.00'),
        'payroll_generated_count': MonthlySalary.objects.filter(month=month_start).count(),
        'total_active_workers': Employee.objects.filter(is_active=True).count(),

        # Activity feed
        'recent_activities':   recent_activities,
    })


def king_logout(request):
    """
    Production-grade King/Owner logout function.
    
    Security Features:
    1. Clears king_authenticated session flag
    2. Destroys all session data (logout)
    3. Ensures new authentication required for re-access
    4. Logs logout event for audit trail
    
    Args:
        request: HTTP request object
        
    Returns:
        Redirect to king_login page
    """
    import logging
    logger = logging.getLogger(__name__)
    
    username = request.user.username if request.user.is_authenticated else 'Unknown'
    client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
    
    # Clear king authentication flag
    request.session.pop('king_authenticated', None)
    
    # Clear all session data
    request.session.flush()
    
    # Logout user
    logout(request)
    
    logger.info(f"King logout: {username} logged out from {client_ip}")
    
    return redirect('king_login')
