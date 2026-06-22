"""Owner (King) view handlers.

Module: king.views
App: king
Purpose: Owner authentication, dashboard analytics, and work order/revenue/ledger
workflows.
Key responsibilities: Owner-only access control, KPI aggregation, and export
flows for ledger reporting.
Dependencies: king models, payroll/attendance/billing/expenses aggregates, and
audit service.
Author note: Security checks are intentionally strict and duplicated at login
and decorator layers.
"""

# ============================================================
# IMPORTS
# ============================================================
import calendar
import io
import json
import logging
from datetime import date, datetime, timedelta
from datetime import date as date_class
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.cache import cache
from xhtml2pdf import pisa
from decimal import Decimal as _D

from employees.models import Employee
from attendance.models import Attendance
from billing.models import Bill
from expenses.models import Expense
from king.models import Revenue as ManualRevenue
from payroll.models import MonthlySalary, Advance
from portal.decorators import king_required

from .models import LedgerEntry, Revenue, WorkOrder, LedgerAccount
from portal.models import BrandSettings
from analytics.services.audit_service import create_audit_log
from analytics.services.audit_service import recent_activity_items_for_king


# ============================================================
# AUTHENTICATION
# ============================================================

def king_login(request):
    """Authenticate owner-only access for the King portal.

    Args:
        request (HttpRequest): Incoming login request.

    Returns:
        HttpResponse: Login page or redirect to king dashboard.

    Raises:
        None.

    Business Rule:
        Only users in the King group may authenticate; managers are rejected.
    """
    logger = logging.getLogger(__name__)
    
    client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
    
    # Reason: Avoid re-auth prompts for valid king sessions.
    if request.user.is_authenticated and request.session.get('king_authenticated'):
        if request.user.groups.filter(name='King').exists():
            return redirect('king:king_dashboard')
    
    # Reason: Clear stale flags to prevent session reuse.
    if 'king_authenticated' in request.session:
        del request.session['king_authenticated']
    
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        # Reason: Reject empty credentials to avoid noisy auth checks.
        if not username or not password:
            logger.warning(
                f"King login: Empty credentials attempt from {client_ip}"
            )
            messages.error(request, "Username and password are required.")
            return render(request, 'king/king_login.html')
        
        # Reason: Authenticate before any group checks.
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
        
        # Reason: Manager credentials must never access owner portal.
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
        
        # Reason: Only explicit King group membership is allowed.
        is_king = user.groups.filter(name='King').exists()
        is_superuser = user.is_superuser
        
        if is_king:
            # Reason: King group users may authenticate into owner portal.
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
            # Reason: Superusers require explicit King group membership.
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
            logger.warning(
                f"King login: Unauthorized user {username} attempted access from {client_ip}"
            )
            messages.error(
                request,
                "⛔ Owner access only. You are not authorized for this dashboard."
            )
            return render(request, 'king/king_login.html')
    
    return render(request, 'king/king_login.html')
# ============================================================
# DASHBOARD
# ============================================================
@king_required
def king_dashboard(request):
    """Render owner dashboard with KPI aggregates and operational alerts.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Owner dashboard page.

    Raises:
        None.

    Business Rule:
        Dashboard totals use month-to-date data and enforce owner-only access.
    """

    today = date.today()
    now = timezone.now()
    cache_key = (
        f"dashboard:king:{request.user.id}:"
        f"{today.strftime('%Y-%m')}:"
        f"{request.session.session_key or 'anon'}"
    )
    cached_html = cache.get(cache_key)
    if cached_html:
        return HttpResponse(cached_html)

    def calculate_daily_salary_for_employee(employee, target_date):
        """Calculate salary for a single day using payroll logic.

        Args:
            employee (Employee): Employee to calculate for.
            target_date (date): Attendance date.

        Returns:
            Decimal: Daily salary amount (always safe, never crashes).

        Raises:
            None.

        Business Rule:
            Absences and missing attendance return zero to avoid false payouts.
        """
        # Reason: Missing attendance should not generate pay.
        att = Attendance.objects.filter(
            employee=employee,
            date=target_date
        ).first()
        
        if not att:
            return Decimal('0.00')  # No attendance marked
        
        # Reason: Guard against invalid wage values to avoid crashes.
        daily_wage = employee.daily_wage
        if not daily_wage or daily_wage <= 0:
            return Decimal('0.00')  # Invalid wage, return zero
        
        # Reason: Attendance status determines base pay.
        if att.status == 'P':
            day_pay = daily_wage
        elif att.status == 'H':
            day_pay = daily_wage * Decimal('0.5')
        elif att.status == 'A':
            day_pay = Decimal('0.00')  # Absence, no pay (paid leaves handled monthly)
        else:
            day_pay = Decimal('0.00')
        
        # Reason: Role may be missing; default overtime to zero.
        if att.overtime_hours and att.overtime_hours > 0 and employee.role:
            overtime_rate = employee.role.overtime_rate_per_hour
            if overtime_rate:  # Extra safety check for rate being valid
                overtime_pay = att.overtime_hours * overtime_rate
                day_pay += overtime_pay
        
        # Reason: Monetary values must be rounded to two decimals.
        return day_pay.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def calculate_accumulated_salary_for_month(month_start):
        """Calculate accumulated salary for the month, including pending.

        Args:
            month_start (date): First day of the month.

        Returns:
            Decimal: Total net salary (existing + pending).

        Raises:
            None.

        Business Rule:
            Existing payroll is preserved; pending is computed for today only.
        """
        # Reason: Build a bounded date range for month-to-date queries.
        if month_start.month == 12:
            next_month_date = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_date = month_start.replace(month=month_start.month + 1)
        
        # Reason: Existing payroll must be included to avoid double counting.
        existing_total = MonthlySalary.objects.filter(
            month=month_start
        ).aggregate(t=Coalesce(Sum('net_pay'), Decimal('0.00')))['t']
        
        employees_with_payroll = set(
            MonthlySalary.objects.filter(month=month_start).values_list('employee_id', flat=True)
        )
        
        # Reason: Single query prevents N+1 loops on attendance.
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
        
        # Reason: Single query for advances keeps FIFO ordering consistent.
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
        
        # Reason: Compute pending payroll for workers without a generated salary.
        pending_total = Decimal('0.00')
        
        for emp_id, att_data in emp_attendance_map.items():
            # Reason: Avoid double counting employees with generated payroll.
            if emp_id in employees_with_payroll:
                continue
            
            emp = att_data['employee']
            records = att_data['records']
            
            if not records or (emp.daily_wage or Decimal('0.00')) <= 0:
                continue
            
            try:
                # Reason: Single pass reduces per-employee overhead.
                present_count = sum(1 for r in records if r.status == 'P')
                half_day_count = sum(1 for r in records if r.status == 'H')
                absent_count = sum(1 for r in records if r.status == 'A')
                overtime_hours = sum(r.overtime_hours or 0 for r in records)
                
                # Reason: Paid leave logic remains capped for liability control.
                paid_leaves = min(absent_count, 2)
                
                # Reason: Use Decimal for monetary accuracy.
                daily_wage = emp.daily_wage or Decimal('0.00')
                present_pay = present_count * daily_wage
                half_day_pay = half_day_count * (daily_wage * Decimal('0.5'))
                paid_leave_pay = paid_leaves * daily_wage
                
                # Reason: Role may be missing; default overtime to zero.
                overtime_rate = emp.role.overtime_rate_per_hour if emp.role else Decimal('0.00')
                overtime_pay = Decimal(str(overtime_hours)) * (overtime_rate or Decimal('0.00'))
                
                gross_pay = (present_pay + half_day_pay + paid_leave_pay + overtime_pay).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
                
                # Reason: FIFO advance deductions align with payroll rules.
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
        
        # Reason: Standardize to two-decimal precision.
        total = (existing_total + pending_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return total
    
    def get_todays_daily_salary():
        """Get total salary generated today for all employees.

        Returns:
            Decimal: Total of daily salaries for today.

        Business Rule:
            Daily pay is based strictly on today's attendance records.
        """
        today_attendance = Attendance.objects.filter(
            date=today
        ).select_related('employee__role')
        
        total_salary = Decimal('0.00')
        
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
            
            # Reason: Overtime defaults to zero when role is missing.
            if att.overtime_hours and emp.role:
                overtime_rate = emp.role.overtime_rate_per_hour or Decimal('0.00')
                day_pay += att.overtime_hours * overtime_rate
            
            total_salary += day_pay
        
        return total_salary.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def get_todays_attendance_status(total_emp_count):
        """Get attendance count for today using a single aggregate query.

        Args:
            total_emp_count (int): Total active employees.

        Returns:
            dict: Attendance summary for today.
        """
        # Reason: Aggregate in one query to reduce DB load.
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
    
    # Reason: Provide contextual greeting in the UI header.
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
        """Return rounded month-over-month percent change with zero-division guard."""
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

    wo_summary = WorkOrder.objects.aggregate(
        total_value=Coalesce(Sum('order_value'), Decimal('0.00')),
    )
    total_wo_value = wo_summary['total_value']

    # Revenue received across ALL work orders (sum of Revenue entries linked to WOs)
    revenue_received_on_wo = Revenue.objects.filter(
        work_order__isnull=False
    ).aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total']

    # Also count unlinked manual revenue (revenue with no WO) separately — keep this
    # as "other income"; the WO completion is purely WO-linked revenue vs WO value
    wo_pending_value = max(total_wo_value - revenue_received_on_wo, Decimal('0.00'))

    # WO completion percentage (for the progress bar)
    wo_completion_pct = (
        round((float(revenue_received_on_wo) / float(total_wo_value)) * 100, 1)
        if total_wo_value > 0 else 0
    )

    # Count of work orders by status
    wo_count_summary = WorkOrder.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        completed=Count('id', filter=Q(status='completed')),
        pending=Count('id', filter=Q(status='pending')),
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
    activity_cache_key = f"activity:king:{request.user.id}"
    recent_activities = cache.get(activity_cache_key)
    if recent_activities is None:
        recent_activities = recent_activity_items_for_king(limit=8)
        cache.set(activity_cache_key, recent_activities, timeout=300)
    
    # ── Context ───────────────────────────────────────────────────
    context = {
        'today':               today,
        'time_of_day':         time_of_day,
        'show_payroll_reminder': now.day == calendar.monthrange(now.year, now.month)[1],
        "current_month":        now,

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

        #workorder metrics
        'total_wo_value':         total_wo_value,
        'revenue_received_on_wo': revenue_received_on_wo,
        'wo_pending_value':       wo_pending_value,
        'wo_completion_pct':      wo_completion_pct,
        'wo_count_summary':       wo_count_summary,

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
    }

    html = render_to_string('king/king_dashboard.html', context, request=request)
    cache.set(cache_key, html, timeout=300)
    return HttpResponse(html)


@king_required
def king_recent_activity_api(request):
    """Return recent activity items for the King dashboard.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        JsonResponse: Recent activity payload.

    Raises:
        None.

    Business Rule:
        Activity feed is owner-only and sourced from audit logs.
    """
    cache_key = f"activity:king:{request.user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({'activities': cached, 'cached': True})

    activities = recent_activity_items_for_king(limit=8)
    cache.set(cache_key, activities, timeout=300)
    return JsonResponse({'activities': activities, 'cached': False})


def king_logout(request):
    """Log out King user and clear owner-specific session state.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Redirect to king login page.

    Raises:
        None.

    Business Rule:
        Owner logout clears the king_authenticated flag and session data.
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
    
    # Reason: Ensure owner-only session flag is cleared on logout.
    request.session.pop('king_authenticated', None)
    
    # Reason: Remove all session state to prevent reuse.
    request.session.flush()
    
    logout(request)
    
    logger.info(f"King logout: {username} logged out from {client_ip}")
    
    return redirect('king:king_login')



# ============================================================
# WORK ORDERS
# ============================================================

@king_required
def workorder_dashboard(request):
    """List and summarize work orders with optional month filtering.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Work order dashboard page.

    Raises:
        None.

    Business Rule:
        Month filter scopes the list to the selected work order start date.
    """
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

    # Reason: Summary cards depend on aggregated counts.
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
    """Create a new work order record from owner form input.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Work order form or redirect on success.

    Raises:
        ValidationError: When model validation fails.

    Business Rule:
        Work orders are owner-managed and created from posted form data.
    """
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
    """Show one work order with linked revenue and completion metrics.

    Args:
        request (HttpRequest): Incoming request.
        wo_id (int): WorkOrder id.

    Returns:
        HttpResponse: Work order detail view.

    Raises:
        Http404: When the work order does not exist.
    """
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
    """Update an existing work order and persist edited business details.

    Args:
        request (HttpRequest): Incoming request.
        wo_id (int): WorkOrder id.

    Returns:
        HttpResponse: Work order form or redirect on success.

    Raises:
        Http404: When the work order does not exist.
    """
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
    """Quick status update from dashboard.

    Args:
        request (HttpRequest): Incoming request.
        wo_id (int): WorkOrder id.

    Returns:
        HttpResponse: Redirect to work order dashboard.
    """
    wo = get_object_or_404(WorkOrder, id=wo_id)
    new_status = request.POST.get('status')
    if new_status in dict(WorkOrder.STATUS_CHOICES):
        wo.status = new_status
        wo.save()
        messages.success(request, f'Status updated to {wo.get_status_display()}.')
    return redirect('king:workorder_dashboard')


# ============================================================
# MANUAL REVENUE
# ============================================================

@king_required
def revenue_dashboard(request):
    """Render manual revenue register with monthly totals and category breakdown.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Revenue dashboard page.

    Raises:
        None.
    """
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

    # Reason: Category breakdown drives pie chart data.
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
    """Insert a new revenue entry and optionally link it to a work order.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Redirect to revenue dashboard.

    Raises:
        ValidationError: When posted data is invalid.
    """
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
    """Delete a revenue entry by id from owner dashboard actions.

    Args:
        request (HttpRequest): Incoming request.
        rev_id (int): Revenue id.

    Returns:
        HttpResponse: Redirect to revenue dashboard.
    """
    rev = get_object_or_404(Revenue, id=rev_id)
    rev.delete()
    messages.success(request, 'Revenue entry deleted.')
    return redirect('king:revenue_dashboard')


# ─────────────────────────────────────────────────────────────────────────────
# LEDGER ACCOUNT (PARTY MASTER) VIEWS
# ─────────────────────────────────────────────────────────────────────────────
 
@king_required
def account_list(request):
    """List ledger accounts (parties) for the owner.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Account list page with work order options.

    Raises:
        None.

    Business Rule:
        Owners can only view accounts they created.
    """
    # Reason: Ledger accounts are owner-scoped for audit safety.
    accounts = LedgerAccount.objects.filter(
        created_by=request.user
    ).order_by('name')
    return render(request, 'king/account_list.html', {
        'accounts':    accounts,
        'work_orders': WorkOrder.objects.order_by('wo_number'),
    })
 
 
@king_required
@require_POST
def account_add(request):
    """Create a new ledger account (party).

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Redirect to account list.

    Raises:
        None.

    Business Rule:
        Party names must be unique (case-insensitive).
    """
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Party name is required.')
        return redirect('king:account_list')
 
    if LedgerAccount.objects.filter(name__iexact=name).exists():
        messages.error(request, f'An account named "{name}" already exists.')
        return redirect('king:account_list')
 
    wo_id = request.POST.get('work_order') or None
    LedgerAccount.objects.create(
        name       = name,
        address    = request.POST.get('address') or None,
        gst_number = request.POST.get('gst_number') or None,
        phone      = request.POST.get('phone') or None,
        work_order = WorkOrder.objects.filter(id=wo_id).first() if wo_id else None,
        created_by = request.user,
    )
    messages.success(request, f'Account "{name}" created.')
    return redirect('king:account_list')
 
 
@king_required
@require_POST
def account_edit(request, account_id):
    """Update an existing ledger account.

    Args:
        request (HttpRequest): Incoming request.
        account_id (int): LedgerAccount id.

    Returns:
        HttpResponse: Redirect to account list.

    Raises:
        Http404: When the account does not exist.

    Business Rule:
        Party names must remain unique across accounts.
    """
    acc = get_object_or_404(LedgerAccount, id=account_id)
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Party name is required.')
        return redirect('king:account_list')
 
    # Check uniqueness excluding self
    if LedgerAccount.objects.filter(name__iexact=name).exclude(id=account_id).exists():
        messages.error(request, f'Another account named "{name}" already exists.')
        return redirect('king:account_list')
 
    wo_id = request.POST.get('work_order') or None
    acc.name       = name
    acc.address    = request.POST.get('address') or None
    acc.gst_number = request.POST.get('gst_number') or None
    acc.phone      = request.POST.get('phone') or None
    acc.work_order = WorkOrder.objects.filter(id=wo_id).first() if wo_id else None
    acc.save()
    messages.success(request, f'Account "{name}" updated.')
    return redirect('king:account_list')
 
 
@king_required
@require_POST
def account_delete(request, account_id):
    """Delete a ledger account and keep entries unassigned.

    Args:
        request (HttpRequest): Incoming request.
        account_id (int): LedgerAccount id.

    Returns:
        HttpResponse: Redirect to account list.

    Raises:
        Http404: When the account does not exist.

    Business Rule:
        Ledger entries are preserved; account is cleared to avoid data loss.
    """
    acc = get_object_or_404(LedgerAccount, id=account_id)
    name = acc.name
    acc.delete()
    messages.success(
        request,
        f'Account "{name}" deleted. Linked entries are now unassigned.',
    )
    return redirect('king:account_list')



# ============================================================
# LEDGER
# ============================================================

def _to_decimal(value):
    """Normalize nullable numeric values into Decimal for safe financial math.

    Args:
        value (Any): Input value to normalize.

    Returns:
        Decimal: Normalized monetary value.
    """
    if value is None:
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _format_indian_amount(value):
    """Format Decimal amounts using Indian grouping and 2-decimal precision.

    Args:
        value (Any): Value to format.

    Returns:
        str: Formatted amount string.
    """
    amount = _to_decimal(value).quantize(Decimal('0.01'))
    sign = '-' if amount < 0 else ''
    amount = abs(amount)

    int_part, dec_part = f"{amount:.2f}".split('.')
    if len(int_part) <= 3:
        grouped = int_part
    else:
        last_three = int_part[-3:]
        rest = int_part[:-3]
        chunks = []
        while len(rest) > 2:
            chunks.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            chunks.insert(0, rest)
        grouped = ','.join(chunks + [last_three])

    return f"{sign}{grouped}.{dec_part}"


def _short_type(entry_type):
    """Return compact labels for ledger entry type badges.

    Args:
        entry_type (str): Ledger entry type.

    Returns:
        str: Short display label.
    """
    return {
        'sale': 'Sale',
        'receipt': 'Rcpt',
        'payment': 'Pmt',
        'journal': 'Jrnl',
    }.get(entry_type, (entry_type or '').title())


# ─────────────────────────────────────────────────────────────────────────────
# LEDGER VIEWS  (replace existing versions)
# ─────────────────────────────────────────────────────────────────────────────
 
def _ledger_data(from_date, to_date, account_id=None):
    """Build ledger rows, running balances, and totals for a date range.

    Args:
        from_date (date): Start date (inclusive).
        to_date (date): End date (inclusive).
        account_id (int | None): Optional LedgerAccount id filter.

    Returns:
        dict: Aggregated ledger rows and totals for rendering.

    Raises:
        None.

    Business Rule:
        Ledger rows are ordered by value date then creation for audit order.
    """
    qs = LedgerEntry.objects.filter(
        date__gte=from_date,
        date__lte=to_date,
    )
    if account_id:
        qs = qs.filter(account_id=account_id)
    # Reason: Stable ordering preserves running balance auditability.
    entries = qs.order_by('date', 'created_at')
 
    running_balance = Decimal('0.00')
    rows = []
    total_debit  = Decimal('0.00')
    total_credit = Decimal('0.00')
 
    for entry in entries:
        debit  = _to_decimal(entry.debit)
        credit = _to_decimal(entry.credit)
        running_balance += (debit - credit)
        total_debit     += debit
        total_credit    += credit
 
        balance_type       = 'Dr' if running_balance >= 0 else 'Cr'
        particulars_prefix = 'Dr' if debit > 0 else 'Cr'
 
        rows.append({
            'entry': entry,
            'type_short': _short_type(entry.entry_type),
            'particulars_with_prefix': f"{particulars_prefix}  {entry.particulars}",
            'value_date':  entry.value_date,
            'branch_code': entry.branch_code or '',
            'debit_fmt':   _format_indian_amount(debit)  if debit  > 0 else '',
            'credit_fmt':  _format_indian_amount(credit) if credit > 0 else '',
            'balance_fmt': _format_indian_amount(abs(running_balance)),
            'balance_type': balance_type,
            'balance_display': f"{_format_indian_amount(abs(running_balance))}{balance_type}",
        })
 
    debit_balance = total_debit - total_credit
    if debit_balance < 0:
        debit_balance = Decimal('0.00')
 
    grand_total = total_debit if total_debit >= total_credit else total_credit
 
    return {
        'entries':           entries,
        'rows':              rows,
        'total_debit':       total_debit,
        'total_credit':      total_credit,
        'debit_balance':     debit_balance,
        'grand_total':       grand_total,
        'total_debit_fmt':   _format_indian_amount(total_debit),
        'total_credit_fmt':  _format_indian_amount(total_credit),
        'debit_balance_fmt': _format_indian_amount(debit_balance),
        'grand_total_fmt':   _format_indian_amount(grand_total),
    }

@king_required
def ledger_view(request):
    """Render owner ledger with party filtering and running Dr/Cr balance.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Ledger view page.

    Raises:
        None.

    Business Rule:
        Date range is normalized and audited for owner visibility.
    """
    from_date_str = request.GET.get('from_date')
    to_date_str   = request.GET.get('to_date')
    account_id    = request.GET.get('account_id') or None
 
    today     = date_class.today()
    from_date = date_class.fromisoformat(from_date_str) if from_date_str else today.replace(day=1)
    to_date   = date_class.fromisoformat(to_date_str)   if to_date_str   else today
    if from_date > to_date:
        from_date, to_date = to_date, from_date
 
    # Resolve selected account
    selected_account = None
    if account_id:
        selected_account = LedgerAccount.objects.filter(id=account_id).first()
 
    data = _ledger_data(from_date, to_date, account_id=account_id)
 
    # Reason: Account picker must include all parties for owner.
    all_accounts = LedgerAccount.objects.order_by('name')

    brand = BrandSettings.objects.first()

    company_name = brand.company_name if brand else 'CWMS System'
    company_address = brand.company_address if brand else ''
    company_gstin = brand.company_gstin if brand else ''
 
    create_audit_log(
        user=request.user,
        username=request.user.username,
        activity='system',
        action='view',
        entity_type='Ledger',
        entity_id=0,
        entity_name='Ledger View',
        details=f"Viewed ledger from {from_date} to {to_date}" + (
            f" for account {selected_account.name}" if selected_account else ""
        ),
        request=request,
    )
 
    return render(request, 'king/ledger.html', {
        'ledger_rows':       data['rows'],
        'from_date':         from_date,
        'to_date':           to_date,
        'entry_types':       LedgerEntry.ENTRY_TYPE_CHOICES,
        'company_name':      company_name,
        'company_address':   company_address,
        'company_gstin':     company_gstin,
        'total_debit_fmt':   data['total_debit_fmt'],
        'total_credit_fmt':  data['total_credit_fmt'],
        'debit_balance_fmt': data['debit_balance_fmt'],
        'grand_total_fmt':   data['grand_total_fmt'],
        'now':               datetime.now(),
        'all_accounts':      all_accounts,
        'selected_account':  selected_account,
        'account_id':        account_id or '',
    })


@king_required
@require_POST
def ledger_add_entry(request):
    """Create a ledger transaction row linked to a party account.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Redirect to ledger view.

    Raises:
        ValidationError: When posted data is invalid.

    Business Rule:
        Ledger entries preserve user-entered voucher metadata for audits.
    """
    debit    = request.POST.get('debit')  or '0'
    credit   = request.POST.get('credit') or '0'
    date_str = request.POST.get('date')
    vd_str   = request.POST.get('value_date') or None
    acc_id   = request.POST.get('account')    or None
    wo_id    = request.POST.get('work_order') or None
 
    # Preserve the account filter on redirect so user stays on same party view
    account_id_param = f"?account_id={acc_id}" if acc_id else ""
 
    try:
        actual_date  = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.localdate()
        actual_vdate = datetime.strptime(vd_str,   '%Y-%m-%d').date() if vd_str   else None
 
        linked_account = LedgerAccount.objects.filter(id=acc_id).first() if acc_id else None
        linked_wo      = WorkOrder.objects.filter(id=wo_id).first()       if wo_id else None
 
        entry = LedgerEntry.objects.create(
            date           = actual_date,
            value_date     = actual_vdate,
            entry_type     = request.POST.get('entry_type'),
            voucher_number = request.POST.get('voucher_number') or None,
            particulars    = request.POST.get('particulars'),
            branch_code    = request.POST.get('branch_code') or None,
            debit          = Decimal(debit),
            credit         = Decimal(credit),
            account        = linked_account,
            work_order     = linked_wo,
            created_by     = request.user,
        )
    except (ValidationError, ValueError) as exc:
        messages.error(request, f'Unable to add ledger entry: {exc}')
        base_url = reverse('king:ledger')
        return redirect(f"{base_url}{account_id_param}")
 
    create_audit_log(
        user=request.user,
        username=request.user.username,
        activity='system',
        action='create',
        entity_type='LedgerEntry',
        entity_id=entry.id,
        entity_name=entry.voucher_number or f"Entry-{entry.id}",
        details=f"Created ledger entry {entry.entry_type} on {entry.date}",
        request=request,
    )
 
    messages.success(request, 'Ledger entry added.')
    # Redirect back preserving account filter
    base_url = reverse('king:ledger')
    redirect_url = f"{base_url}?account_id={acc_id}" if acc_id else base_url
    return redirect(redirect_url)


@king_required
@require_POST
def ledger_delete_entry(request, entry_id):
    """Delete a ledger entry and write an audit trail event.

    Args:
        request (HttpRequest): Incoming request.
        entry_id (int): LedgerEntry id.

    Returns:
        HttpResponse: Redirect to ledger view.
    """
    entry = get_object_or_404(LedgerEntry, id=entry_id)
    entry_name = entry.voucher_number or f"Entry-{entry.id}"
    entry.delete()

    create_audit_log(
        user=request.user,
        username=request.user.username,
        activity='system',
        action='delete',
        entity_type='LedgerEntry',
        entity_id=entry_id,
        entity_name=entry_name,
        details='Deleted ledger entry',
        request=request,
    )

    messages.success(request, 'Entry deleted.')
    return redirect('king:ledger')


@king_required
def ledger_pdf(request):
    """Export party-filtered ledger as PDF.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: PDF response with ledger export.

    Raises:
        None.

    Business Rule:
        Export uses the same date range and account filter as the ledger view.
    """
    from_date_str = request.GET.get('from_date')
    to_date_str   = request.GET.get('to_date')
    account_id    = request.GET.get('account_id') or None
 
    today     = date_class.today()
    from_date = date_class.fromisoformat(from_date_str) if from_date_str else today.replace(day=1)
    to_date   = date_class.fromisoformat(to_date_str)   if to_date_str   else today
    if from_date > to_date:
        from_date, to_date = to_date, from_date
 
    selected_account = None
    if account_id:
        selected_account = LedgerAccount.objects.filter(id=account_id).first()
 
    data = _ledger_data(from_date, to_date, account_id=account_id)

    # Prefer explicit URL value, then selected account name.
    account_name = (request.GET.get('account_name') or '').strip()
    if not account_name and selected_account:
        account_name = selected_account.name

    # Pull party GST from latest entry snapshot when present; fallback to account master GST.
    latest_entry = data['entries'].order_by('-date', '-created_at').first()
    party_gstin = (getattr(latest_entry, 'gst_snapshot', '') or '').strip() if latest_entry else ''
    if not party_gstin and selected_account:
        party_gstin = (selected_account.gst_number or '').strip()

    # Use account master address as party address fallback.
    party_address = (selected_account.address or '').strip() if selected_account else ''

    brand = BrandSettings.objects.first()

    company_name = brand.company_name if brand else 'CWMS System'
    company_address = brand.company_address if brand else ''
    company_gstin = brand.company_gstin if brand else ''
 
    template = get_template('king/ledger_pdf.html')
    html = template.render({
        'ledger_rows':       data['rows'],
        'from_date':         from_date,
        'to_date':           to_date,
        'company_name':      company_name,
        'company_address':   company_address,
        'company_gstin':     company_gstin,
        'account_name':      account_name,
        'party_gstin':       party_gstin,
        'party_address':     party_address,
        'selected_account':  selected_account,
        'total_debit_fmt':   data['total_debit_fmt'],
        'total_credit_fmt':  data['total_credit_fmt'],
        'debit_balance_fmt': data['debit_balance_fmt'],
        'grand_total_fmt':   data['grand_total_fmt'],
    })
 
    result = io.BytesIO()
    pisa.CreatePDF(html, dest=result)
 
    party_slug = selected_account.name.replace(' ', '_') if selected_account else 'all'
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="ledger_{party_slug}_{from_date}_to_{to_date}.pdf"'
    )
 
    create_audit_log(
        user=request.user,
        username=request.user.username,
        activity='system',
        action='export',
        entity_type='Ledger',
        entity_id=0,
        entity_name='Ledger PDF',
        details=f"Exported ledger PDF from {from_date} to {to_date}" + (
            f" for {selected_account.name}" if selected_account else ""
        ),
        request=request,
    )
 
    return response

