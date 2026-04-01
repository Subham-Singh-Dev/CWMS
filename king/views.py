# king/views.py
from decimal import ROUND_HALF_UP, Decimal
import io
import json
import logging
from datetime import date, datetime, timedelta
from datetime import date as date_class
from tokenize import group

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template
from django.utils import timezone
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from employees.models import Employee
from attendance.models import Attendance
from billing.models import Bill
from expenses.models import Expense
from king.models import Revenue as ManualRevenue
from payroll.models import MonthlySalary, Advance
from portal.decorators import king_required

from .models import WorkOrder, Revenue, LedgerEntry
from analytics.services.audit_service import recent_activity_items_for_king, create_audit_log






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
    
    logger = logging.getLogger(__name__)
    
    client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
    
    # If already authenticated with valid session flag, redirect to dashboard
    if request.user.is_authenticated and request.session.get('king_authenticated'):
        if request.user.groups.filter(name='King').exists():
            return redirect('king:king_dashboard')
    
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
            return render(request, 'king/king_login.html')
        
        # AUTHENTICATION: Check credentials
        user = authenticate(request, username=username, password=password)
        
        if user is None:
            # Log failed authentication
            logger.warning(
                f"King login: Failed authentication for {username} from {client_ip}"
            )
            create_audit_log(
                user=None,
                username=username or 'UNKNOWN',
                activity='user',
                action='login',
                entity_type='User',
                entity_id=0,
                entity_name=username or 'UNKNOWN',
                details='Failed King login',
                status='error',
                error_message='Invalid username or password',
                request=request,
            )
            messages.error(request, "Invalid username or password.")
            return render(request, 'king/king_login.html')
        
        if not user.is_active:
            logger.warning(
                f"King login: Inactive user {username} attempted access from {client_ip}"
            )
            messages.error(request, "Your account is inactive. Contact administrator.")
            return render(request, 'king/king_login.html')
        
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
            return render(request, 'king/king_login.html')
        
        # CRITICAL SECURITY CHECK 2: VERIFY King group membership
        is_king = user.groups.filter(name='King').exists()
        is_superuser = user.is_superuser
        
        if is_king:
            # User has explicit King group - ALLOW LOGIN
            login(request, user)
            request.session['king_authenticated'] = True
            request.session.set_expiry(3600)  # 1 hour session timeout for security

            create_audit_log(
                user=user,
                username=user.username,
                activity='user',
                action='login',
                entity_type='User',
                entity_id=user.id,
                entity_name=user.username,
                details='King login success',
                request=request,
            )
            
            logger.info(
                f"King login: Successful authentication for {username} from {client_ip}"
            )
            messages.success(request, f"Welcome back, Owner {username}!")
            return redirect('king:king_dashboard')
        
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
            return render(request, 'king/king_login.html')
        
        else:
            # Regular user without King group - REJECT
            logger.warning(
                f"King login: Unauthorized user {username} attempted access from {client_ip}"
            )
            messages.error(
                request,
                "⛔ Owner access only. You are not authorized for this dashboard."
            )
            return render(request, 'king/king_login.html')
    
    # GET request: Render login form
    return render(request, 'king/king_login.html')


#(only king_dashboard changes)


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
        ROUND_HALF_UP
        
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
    # ── Helper function: Calculate accumulated salary (OPTIMIZED - NO LOOPS) ──
    def calculate_accumulated_salary_for_month(month_start):
        """
        OPTIMIZED VERSION - Uses single database query instead of N+1 loops.
        Combines all attendance for the month, then processes in Python.
        
        Args:
            month_start: First day of month
            
        Returns:
            Decimal: Total net salary (existing + pending)
        """
        
        # Get next month boundary
        if month_start.month == 12:
            next_month_date = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_date = month_start.replace(month=month_start.month + 1)
        
        # STEP 1: Get existing payroll (single query) ✅
        existing_total = MonthlySalary.objects.filter(
            month=month_start
        ).aggregate(t=Coalesce(Sum('net_pay'), Decimal('0.00')))['t']
        
        employees_with_payroll = set(
            MonthlySalary.objects.filter(month=month_start).values_list('employee_id', flat=True)
        )
        
        # STEP 2: Fetch ALL attendance data for this month in ONE query ✅
        all_attendance = Attendance.objects.filter(
            date__gte=month_start,
            date__lt=next_month_date,
            date__lte=today
        ).select_related('employee__role')
        
        # Group attendance by employee
        emp_attendance_map = {}
        for att in all_attendance:
            emp_id = att.employee_id
            if emp_id not in emp_attendance_map:
                emp_attendance_map[emp_id] = {'employee': att.employee, 'records': []}
            emp_attendance_map[emp_id]['records'].append(att)
        
        # STEP 3: Fetch ALL advances in ONE query ✅
        all_advances = Advance.objects.filter(
            settled=False
        ).select_related('employee').order_by('issued_date')
        
        # Group advances by employee
        emp_advances_map = {}
        for adv in all_advances:
            emp_id = adv.employee_id
            if emp_id not in emp_advances_map:
                emp_advances_map[emp_id] = []
            emp_advances_map[emp_id].append(adv)
        
        # STEP 4: Calculate pending payroll from grouped data
        pending_total = Decimal('0.00')
        
        for emp_id, att_data in emp_attendance_map.items():
            # Skip if already has generated payroll
            if emp_id in employees_with_payroll:
                continue
            
            emp = att_data['employee']
            records = att_data['records']
            
            if not records or (emp.daily_wage or Decimal('0.00')) <= 0:
                continue
            
            try:
                # Count attendance (single pass through records)
                present_count = sum(1 for r in records if r.status == 'P')
                half_day_count = sum(1 for r in records if r.status == 'H')
                absent_count = sum(1 for r in records if r.status == 'A')
                overtime_hours = sum(r.overtime_hours or 0 for r in records)
                
                # Paid leave logic
                paid_leaves = min(absent_count, 2)
                
                # Gross pay
                daily_wage = emp.daily_wage or Decimal('0.00')
                present_pay = present_count * daily_wage
                half_day_pay = half_day_count * (daily_wage * Decimal('0.5'))
                paid_leave_pay = paid_leaves * daily_wage
                
                # Overtime
                overtime_rate = emp.role.overtime_rate_per_hour if emp.role else Decimal('0.00')
                overtime_pay = Decimal(str(overtime_hours)) * (overtime_rate or Decimal('0.00'))
                
                gross_pay = (present_pay + half_day_pay + paid_leave_pay + overtime_pay).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
                
                # Apply FIFO advance deductions
                net_pay = gross_pay
                for advance in emp_advances_map.get(emp_id, []):
                    if net_pay <= 0:
                        break
                    deduction = min(net_pay, advance.remaining_amount)
                    net_pay -= deduction
                
                pending_total += net_pay
                
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Error calculating salary for {emp.name}: {str(e)}")
                continue
        
        # Return total
        total = (existing_total + pending_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return total
    
    # ── Helper function: Get today's daily salary (OPTIMIZED) ──
    def get_todays_daily_salary():
        """Get total salary generated today for all employees using database aggregation"""
        
        today_attendance = Attendance.objects.filter(
            date=today
        ).select_related('employee__role')
        
        total_salary = Decimal('0.00')
        
        # Single query to get today's salary calculation
        for att in today_attendance:
            emp = att.employee
            daily_wage = emp.daily_wage or Decimal('0.00')
            
            if att.status == 'P':
                day_pay = daily_wage
            elif att.status == 'H':
                day_pay = daily_wage * Decimal('0.5')
            elif att.status == 'A':
                day_pay = Decimal('0.00')
            else:
                day_pay = Decimal('0.00')
            
            # Add overtime
            if att.overtime_hours and emp.role:
                overtime_rate = emp.role.overtime_rate_per_hour or Decimal('0.00')
                day_pay += att.overtime_hours * overtime_rate
            
            total_salary += day_pay
        
        return total_salary.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # ── Helper function: Get today's attendance status (OPTIMIZED) ──
    def get_todays_attendance_status(total_emp_count):
        """Get attendance count for today using single database query"""

        # Single query to get all counts at once
        today_stats = Attendance.objects.filter(date=today).aggregate(
            present=Count('id', filter=Q(status='P')),
            absent=Count('id', filter=Q(status='A')),
            half_day=Count('id', filter=Q(status='H'))
        )
        
        present_count = today_stats['present']
        absent_count = today_stats['absent']
        half_day_count = today_stats['half_day']
        total_marked = present_count + absent_count + half_day_count
        
        return {
            'marked': total_marked > 0,
            'present': present_count,
            'absent': absent_count,
            'half_day': half_day_count,
            'total_marked': total_marked,
            'total_employees': total_emp_count
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


    # ── Helpers ───────────────────────────────────────────────────
    def pct_change(current, previous):
        if not previous or float(previous) == 0:
            return 0
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
    # Calculate unpaid salaries for CURRENT MONTH (matching manager dashboard)
    cur_month_payroll = MonthlySalary.objects.filter(
        month=month_start
    ).aggregate(
        total_net=Coalesce(Sum('net_pay'), Decimal('0.00')),
        total_paid=Coalesce(Sum('net_pay', filter=Q(is_paid=True)), Decimal('0.00'))
    )
    
    # Current month liability = total net - what's been paid
    total_liability = (cur_month_payroll['total_net'] - cur_month_payroll['total_paid']) or Decimal('0.00')

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

    payroll_deductions = MonthlySalary.objects.filter(month=month_start).aggregate(
        total_pf=Coalesce(Sum('pf_deduction'), Decimal('0.00')),
        total_esic=Coalesce(Sum('esic_deduction'), Decimal('0.00')),
    )

    monthly_pf_deduction = payroll_deductions['total_pf']
    monthly_esic_deduction = payroll_deductions['total_esic']

    if monthly_pf_deduction > 0:
        expense_cat_labels.append('PF Deduction (Payroll)')
        expense_cat_data.append(float(monthly_pf_deduction))

    if monthly_esic_deduction > 0:
        expense_cat_labels.append('ESIC Deduction (Payroll)')
        expense_cat_data.append(float(monthly_esic_deduction))
    
    # Replace cur_revenue with yearly manual revenue only
    year_start = date(today.year, 1, 1)
    year_end   = date(today.year + 1, 1, 1)

    cur_revenue = float(
        ManualRevenue.objects.filter(
            date__gte=year_start, date__lt=year_end
        ).aggregate(t=Sum('amount'))['t'] or 0
    )

    # ── Billing (Revenue = paid bills this month) ─────────────────
    billing_revenue  = Bill.objects.filter(
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
        status__in=['P', 'H']  # P = Present, H = Half-day
    ).count()
    attendance_rate = round((total_present / total_possible) * 100, 1)

    # ── Net Profit ────────────────────────────────────────────────
    net_profit      = float(cur_revenue) - float(cur_expenses) - float(cur_payroll)
    profit_margin   = round((net_profit / float(cur_revenue)) * 100, 1) if float(cur_revenue) > 0 else 0

    # ── Optimised 6-month chart (3 queries total, not 18) ──────────
    six_months_ago = date(today.year, today.month, 1) - timedelta(days=150)

    rev_by_month = {
        r['m'].strftime('%Y-%m'): r['t']
        for r in Revenue.objects
            .filter(date__gte=six_months_ago)
            .annotate(m=TruncMonth('date'))
            .values('m')
            .annotate(t=Sum('amount'))
    }
    exp_by_month = {
        r['m'].strftime('%Y-%m'): r['t']
        for r in Expense.objects
            .filter(date__gte=six_months_ago)
            .annotate(m=TruncMonth('date'))
            .values('m')
            .annotate(t=Sum('amount'))
    }
    sal_by_month = {
        r['month'].strftime('%Y-%m'): r['t']
        for r in MonthlySalary.objects
            .filter(month__gte=six_months_ago)
            .values('month').annotate(t=Sum('net_pay'))
    }

    chart_labels, revenue_data, expense_data, payroll_data = [], [], [], []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y}-{m:02d}"
        chart_labels.append(date(y, m, 1).strftime('%b %y'))
        revenue_data.append(float(rev_by_month.get(key, 0)))
        expense_data.append(float(exp_by_month.get(key, 0)))
        payroll_data.append(float(sal_by_month.get(key, 0)))

    # ── Workforce by role ─────────────────────────────────────────
    role_qs     = (
        Employee.objects.filter(is_active=True)
        .values('role__name')             # ⚠️ verify FK field name
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    role_labels = [r['role__name'] or 'Unknown' for r in role_qs]
    role_counts = [r['count'] for r in role_qs]

    # ── Recent Activity (Audit Log) ───────────────────────────────
    recent_activities = recent_activity_items_for_king(limit=8)

    # ── Context ───────────────────────────────────────────────────
    return render(request, 'king/king_dashboard.html', {
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
        'monthly_pf_deduction': monthly_pf_deduction,
        'monthly_esic_deduction': monthly_esic_deduction,

        # Alerts
        'pending_bills_count':  pending_bills_count,
        'pending_bills_amount': pending_bills_amount,
        'advance_outstanding':  advance_outstanding,

        # ──────────── NEW FEATURES ────────────────────────────
        # 1. DAILY SNAPSHOT
        'todays_attendance':   get_todays_attendance_status(total_workers),
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


@king_required
def king_recent_activity_api(request):
    """Real-time activity feed endpoint for King dashboard."""
    return JsonResponse({
        'activities': recent_activity_items_for_king(limit=8)
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
    
    logger = logging.getLogger(__name__)
    
    username = request.user.username if request.user.is_authenticated else 'Unknown'
    client_ip = request.META.get('REMOTE_ADDR', 'Unknown')

    if request.user.is_authenticated:
        create_audit_log(
            user=request.user,
            username=request.user.username,
            activity='user',
            action='logout',
            entity_type='User',
            entity_id=request.user.id,
            entity_name=request.user.username,
            details='King logout',
            request=request,
        )
    
    # Clear king authentication flag
    request.session.pop('king_authenticated', None)
    
    # Clear all session data
    request.session.flush()
    
    # Logout user
    logout(request)
    
    logger.info(f"King logout: {username} logged out from {client_ip}")
    
    return redirect('king:king_login')



# ─────────────────────────────────────────────
# WORK ORDERS
# ─────────────────────────────────────────────

@king_required
def workorder_dashboard(request):
    selected_month = request.GET.get('month')

    if selected_month:
        try:
            year, month = map(int, selected_month.split('-'))
            m_start = date(year, month, 1)
            m_end   = date(year, month+1, 1) if month < 12 else date(year+1, 1, 1)
            workorders = WorkOrder.objects.filter(
                start_date__gte=m_start, start_date__lt=m_end
            )
        except:
            workorders = WorkOrder.objects.all()
    else:
        workorders = WorkOrder.objects.all()

    # Summary counts
    summary = {
        'total':     workorders.count(),
        'pending':   workorders.filter(status='pending').count(),
        'active':    workorders.filter(status='active').count(),
        'completed': workorders.filter(status='completed').count(),
        'cancelled': workorders.filter(status='cancelled').count(),
        'total_value': workorders.aggregate(t=Sum('order_value'))['t'] or 0,
    }

    return render(request, 'king/workorder_dashboard.html', {
        'workorders':     workorders,
        'summary':        summary,
        'selected_month': selected_month or date.today().strftime('%Y-%m'),
    })


@king_required
def workorder_add(request):
    if request.method == 'POST':
        WorkOrder.objects.create(
            client_name    = request.POST.get('client_name'),
            client_contact = request.POST.get('client_contact') or None,
            project_name   = request.POST.get('project_name'),
            location       = request.POST.get('location'),
            order_value    = Decimal(request.POST.get('order_value')),
            gst_number = request.POST.get('gst_number') or None,
            start_date     = request.POST.get('start_date'),
            end_date       = request.POST.get('end_date'),
            status         = request.POST.get('status', 'pending'),
            description    = request.POST.get('description') or None,
            created_by     = request.user,
        )
        messages.success(request, 'Work order created successfully.')
        return redirect('king:workorder_dashboard')

    return render(request, 'king/workorder_form.html', {
        'title':       'Add Work Order',
        'status_choices': WorkOrder.STATUS_CHOICES,
    })


@king_required
def workorder_detail(request, wo_id):
    wo = get_object_or_404(WorkOrder, id=wo_id)
    revenues = wo.revenues.all()
    total_received = wo.total_revenue_received()
    balance        = wo.balance_remaining()
    completion_pct = round(
        (float(total_received) / float(wo.order_value) * 100), 1
    ) if wo.order_value else 0

    return render(request, 'king/workorder_detail.html', {
        'wo':             wo,
        'revenues':       revenues,
        'total_received': total_received,
        'balance':        balance,
        'completion_pct': completion_pct,
    })


@king_required
def workorder_edit(request, wo_id):
    wo = get_object_or_404(WorkOrder, id=wo_id)

    if request.method == 'POST':
        wo.client_name    = request.POST.get('client_name')
        wo.client_contact = request.POST.get('client_contact') or None
        wo.project_name   = request.POST.get('project_name')
        wo.location       = request.POST.get('location')
        wo.order_value    = Decimal(request.POST.get('order_value'))
        wo.gst_number = request.POST.get('gst_number') or None
        wo.start_date     = request.POST.get('start_date')
        wo.end_date       = request.POST.get('end_date')
        wo.status         = request.POST.get('status')
        wo.description    = request.POST.get('description') or None
        wo.save()
        messages.success(request, 'Work order updated.')
        return redirect('king:workorder_detail', wo_id=wo.id)

    return render(request, 'king/workorder_form.html', {
        'title':          'Edit Work Order',
        'wo':             wo,
        'status_choices': WorkOrder.STATUS_CHOICES,
    })


@king_required
@require_POST
def workorder_status_update(request, wo_id):
    """Quick status toggle from dashboard."""
    wo = get_object_or_404(WorkOrder, id=wo_id)
    new_status = request.POST.get('status')
    if new_status in dict(WorkOrder.STATUS_CHOICES):
        wo.status = new_status
        wo.save()
        messages.success(request, f'Status updated to {wo.get_status_display()}.')
    return redirect('king:workorder_dashboard')


# ─────────────────────────────────────────────
# MANUAL REVENUE
# ─────────────────────────────────────────────

@king_required
def revenue_dashboard(request):
    selected_month = request.GET.get('month')

    if selected_month:
        try:
            year, month = map(int, selected_month.split('-'))
            m_start = date(year, month, 1)
            m_end   = date(year, month+1, 1) if month < 12 else date(year+1, 1, 1)
            revenues = Revenue.objects.filter(
                date__gte=m_start, date__lt=m_end
            )
        except:
            revenues = Revenue.objects.all()
    else:
        today   = date.today()
        m_start = today.replace(day=1)
        m_end   = date(today.year, today.month+1, 1) if today.month < 12 else date(today.year+1, 1, 1)
        revenues = Revenue.objects.filter(date__gte=m_start, date__lt=m_end)

    # Category breakdown
    cat_totals = (
        revenues.values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    cat_data = []
    for item in cat_totals:
        dummy = Revenue(category=item['category'])
        cat_data.append({
            'label': dummy.get_category_display(),
            'total': item['total'],
        })

    total_revenue = revenues.aggregate(t=Sum('amount'))['t'] or 0
    work_orders   = WorkOrder.objects.filter(
        status__in=['pending', 'active']
    ).order_by('wo_number')

    return render(request, 'king/revenue_dashboard.html', {
        'revenues':       revenues,
        'total_revenue':  total_revenue,
        'cat_data':       cat_data,
        'work_orders':    work_orders,
        'selected_month': selected_month or date.today().strftime('%Y-%m'),
        'category_choices':     Revenue.CATEGORY_CHOICES,
        'payment_mode_choices': Revenue.PAYMENT_MODE_CHOICES,
    })


@king_required
@require_POST
def revenue_add(request):
    wo_id = request.POST.get('work_order')
    Revenue.objects.create(
        date         = request.POST.get('date'),
        amount       = Decimal(request.POST.get('amount')),
        source       = request.POST.get('source'),
        category     = request.POST.get('category'),
        payment_mode = request.POST.get('payment_mode'),
        work_order   = WorkOrder.objects.get(id=wo_id) if wo_id else None,
        created_by   = request.user,
    )
    messages.success(request, 'Revenue entry added.')
    return redirect('king:revenue_dashboard')


@king_required
@require_POST
def revenue_delete(request, rev_id):
    rev = get_object_or_404(Revenue, id=rev_id)
    rev.delete()
    messages.success(request, 'Revenue entry deleted.')
    return redirect('king:revenue_dashboard')


# ─────────────────────────────────────────────
# LEDGER
# ─────────────────────────────────────────────

@king_required
def ledger_view(request):
    # Date range filter
    from_date_str = request.GET.get('from_date')
    to_date_str   = request.GET.get('to_date')

    today      = date_class.today()
    from_date  = date_class.fromisoformat(from_date_str) if from_date_str else today.replace(day=1)
    to_date    = date_class.fromisoformat(to_date_str)   if to_date_str   else today

    entries = LedgerEntry.objects.filter(
        date__gte=from_date,
        date__lte=to_date
    ).order_by('date', 'created_at')

    # Compute running balance
    running_balance = 0
    ledger_rows = []
    for entry in entries:
        running_balance += float(entry.credit) - float(entry.debit)
        ledger_rows.append({
            'entry':           entry,
            'balance':         abs(running_balance),
            'balance_type':    'Cr' if running_balance >= 0 else 'Dr',
        })

    total_debit  = entries.aggregate(t=Sum('debit'))['t']  or 0
    total_credit = entries.aggregate(t=Sum('credit'))['t'] or 0
    net_balance  = float(total_credit) - float(total_debit)

    return render(request, 'king/ledger.html', {
        'ledger_rows':  ledger_rows,
        'from_date':    from_date,
        'to_date':      to_date,
        'total_debit':  total_debit,
        'total_credit': total_credit,
        'net_balance':  abs(net_balance),
        'net_type':     'Cr' if net_balance >= 0 else 'Dr',
        'entry_types':  LedgerEntry.ENTRY_TYPE_CHOICES,
        'now':          datetime.now(),
    })


@king_required
@require_POST
def ledger_add_entry(request):
    debit  = request.POST.get('debit')  or '0'
    credit = request.POST.get('credit') or '0'

    LedgerEntry.objects.create(
        date        = request.POST.get('date'),
        entry_type  = request.POST.get('entry_type'),
        voucher_no  = request.POST.get('voucher_no') or None,
        particulars = request.POST.get('particulars'),
        debit       = Decimal(debit),
        credit      = Decimal(credit),
        created_by  = request.user,
    )
    messages.success(request, 'Ledger entry added.')
    return redirect('king:ledger')


@king_required
@require_POST
def ledger_delete_entry(request, entry_id):
    entry = get_object_or_404(LedgerEntry, id=entry_id)
    entry.delete()
    messages.success(request, 'Entry deleted.')
    return redirect('king:ledger')


@king_required
def ledger_pdf(request):
    from_date_str = request.GET.get('from_date')
    to_date_str   = request.GET.get('to_date')

    today     = date_class.today()
    from_date = date_class.fromisoformat(from_date_str) if from_date_str else today.replace(day=1)
    to_date   = date_class.fromisoformat(to_date_str)   if to_date_str   else today

    entries = LedgerEntry.objects.filter(
        date__gte=from_date,
        date__lte=to_date
    ).order_by('date', 'created_at')

    running_balance = 0
    ledger_rows = []
    for entry in entries:
        running_balance += float(entry.credit) - float(entry.debit)
        ledger_rows.append({
            'entry':        entry,
            'balance':      abs(running_balance),
            'balance_type': 'Cr' if running_balance >= 0 else 'Dr',
        })

    total_debit  = entries.aggregate(t=Sum('debit'))['t']  or 0
    total_credit = entries.aggregate(t=Sum('credit'))['t'] or 0
    net_balance  = float(total_credit) - float(total_debit)

    template = get_template('king/ledger_pdf.html')
    html = template.render({
        'ledger_rows':  ledger_rows,
        'from_date':    from_date,
        'to_date':      to_date,
        'total_debit':  total_debit,
        'total_credit': total_credit,
        'net_balance':  abs(net_balance),
        'net_type':     'Cr' if net_balance >= 0 else 'Dr',
    })

    result = io.BytesIO()
    pisa.CreatePDF(html, dest=result)

    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="ledger_{from_date}_to_{to_date}.pdf"'
    )
    return response