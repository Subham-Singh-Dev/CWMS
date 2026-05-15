"""Portal view handlers.

Module: portal.views
App: portal
Purpose: Handles login, worker/manager dashboards, and payroll orchestration.
Key responsibilities: Role-based access control, payroll batching, attendance
bulk operations, and audit logging for portal interactions.
Dependencies: employees, attendance, payroll, audit service, and decorators.
Author note: Ownership/role checks are explicit to prevent cross-portal data
exposure and unauthorized payroll actions.
"""

# ============================================================
# IMPORTS
# ============================================================
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page
from xhtml2pdf import pisa

from analytics.services.audit_service import create_audit_log
from analytics.services.audit_service import recent_activity_items_for_manager
from attendance.models import Attendance
from employees.models import Employee
from payroll.models import Advance, MonthlySalary
from payroll.services import SalaryAlreadyGeneratedError, generate_monthly_salary

from .decorators import manager_required, worker_required

# ============================================================
# WORKER PORTAL VIEWS
# ============================================================

def portal_login(request):
    """Authenticate manager/worker based on selected login mode.

    Args:
        request (HttpRequest): Incoming request with login credentials.

    Returns:
        HttpResponse: Login template or redirect to the correct dashboard.

    Raises:
        None.

    Business Rule:
        Manager/worker login must match the selected login type toggle.
    """
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.groups.filter(
            name='Manager'
        ).exists():
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
                employee = Employee.objects.get(
                    phone_number=login_id, is_active=True
                )
                user = authenticate(
                    request,
                    username=employee.user.username,
                    password=password,
                )
            except Employee.DoesNotExist:
                pass

        if user is not None and user.is_active:
            # Reason: Role is derived from groups to avoid user-provided flags.
            is_manager = user.is_superuser or user.groups.filter(
                name='Manager'
            ).exists()

            # Business rule: Role must match the login type toggle.
            if login_type == 'manager' and not is_manager:
                messages.error(request, "Invalid credentials.")
            elif login_type == 'worker' and is_manager:
                messages.error(request, "Invalid credentials.")
            else:
                login(request, user)
                create_audit_log(
                    user=user,
                    username=user.username,
                    activity='user',
                    action='login',
                    entity_type='User',
                    entity_id=user.id,
                    entity_name=user.username,
                    details=f"Portal login ({login_type})",
                    request=request,
                )
                if is_manager:
                    messages.success(request, "Welcome back, Manager.")
                    return redirect('manager_dashboard')
                return redirect('worker_dashboard')
        else:
            create_audit_log(
                user=None,
                username=login_id or 'UNKNOWN',
                activity='user',
                action='login',
                entity_type='User',
                entity_id=0,
                entity_name=login_id or 'UNKNOWN',
                details=f"Failed portal login ({login_type})",
                status='error',
                error_message='Invalid ID or password',
                request=request,
            )
            messages.error(request, "Invalid ID or Password.")

    return render(request, 'portal/login.html')

@worker_required
def worker_dashboard(request):
    """Render worker-scoped salary dashboard.

    Args:
        request (HttpRequest): Worker request.

    Returns:
        HttpResponse: Worker dashboard with salary list.

    Raises:
        Employee.DoesNotExist: When the user lacks a worker profile.

    Business Rule:
        Worker data is scoped strictly through request.user.employee to prevent IDOR.
    """
    try:
        employee = request.user.employee
        if not employee.is_active:
            raise Employee.DoesNotExist
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')

    # Reason: Scope payroll to current user to avoid cross-employee access.
    salaries = MonthlySalary.objects.filter(employee=employee).order_by('-month')
    return render(
        request,
        'portal/dashboard.html',
        {'employee': employee, 'salaries': salaries},
    )

def worker_logout(request):
    """Logout worker/manager sessions and record the event in audit trail.

    Args:
        request (HttpRequest): Current request.

    Returns:
        HttpResponse: Redirect to portal login page.

    Raises:
        None.

    Business Rule:
        Logout events are always recorded for audit compliance.
    """
    if request.user.is_authenticated:
        create_audit_log(
            user=request.user,
            username=request.user.username,
            activity='user',
            action='logout',
            entity_type='User',
            entity_id=request.user.id,
            entity_name=request.user.username,
            details='Portal logout',
            request=request,
        )
    logout(request)
    return redirect('portal_login')

@worker_required
def worker_profile(request):
    """Render worker profile page.

    Args:
        request (HttpRequest): Worker request.

    Returns:
        HttpResponse: Worker profile page.

    Raises:
        Employee.DoesNotExist: When the user lacks a worker profile.

    Business Rule:
        Missing profiles are logged out to avoid stale accounts.
    """
    # Reason: Avoid rendering with missing or stale employee profiles.
    try:
        employee = request.user.employee
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')

    return render(request, 'portal/profile.html', {'employee': employee})

@worker_required
def worker_attendance(request):
    """Render worker attendance history for recent records.

    Args:
        request (HttpRequest): Worker request.

    Returns:
        HttpResponse: Attendance page with recent entries.

    Raises:
        Employee.DoesNotExist: When the user lacks a worker profile.

    Business Rule:
        Attendance access is scoped to the current worker only.
    """
    # Reason: Avoid rendering with missing or stale employee profiles.
    try:
        employee = request.user.employee
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')
        
    # Reason: Limit history for performance and data relevance.
    logs = Attendance.objects.filter(employee=employee).order_by('-date')[:30]
    return render(request, 'portal/attendance.html', {'logs': logs})

@worker_required
def download_payslip(request, salary_id):
    """Download paid payslip with ownership enforcement for worker accounts.

    Args:
        request (HttpRequest): Requesting user.
        salary_id (int): MonthlySalary id.

    Returns:
        HttpResponse: PDF response for the payslip.

    Raises:
        PermissionDenied: When the user is not authorized or salary is unpaid.

    Business Rule:
        Only managers or the owning worker can access a paid payslip.
    """
    salary = get_object_or_404(
        MonthlySalary.objects.select_related('employee'),
        id=salary_id,
    )

    # Reason: Only managers can bypass worker ownership checks.
    is_manager = request.user.groups.filter(name='Manager').exists()

    if request.user.is_superuser or is_manager:
        pass  # Access granted
    elif hasattr(request.user, 'employee'):
        # Reason: Enforce worker-level ownership isolation.
        if salary.employee != request.user.employee:
            raise PermissionDenied(
                '⛔ You are not authorized to view this payslip.'
            )
        
        # Reason: Payslips are visible only after payment is finalized.
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
# MANAGER PORTAL VIEWS
# ============================================================
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
        request (HttpRequest): Incoming request.
        viewing_as_owner (bool): Whether King user is viewing read-only.
        
    Returns:
        HttpResponse: Rendered manager dashboard template.

    Raises:
        None.

    Business Rule:
        Metrics are computed for the selected month and visible per role.
    """
    context = {}  # always initialize once

    current_time = timezone.now()
    today = current_time.date()
    selected_month = today.replace(day=1)

    # Reason: Used by downstream payroll and summary navigation.
    context['selected_month'] = selected_month.strftime('%Y-%m')
    
    # Reason: Toggle payroll actions based on existing batch for the month.
    month_date = datetime.strptime(
        context['selected_month'], '%Y-%m'
    ).date().replace(day=1)

    payroll_exists = MonthlySalary.objects.filter(
        month=month_date
    ).exists()

    context['payroll_exists'] = payroll_exists
    # Reason: Template uses this flag to prevent write actions in owner view.
    context['viewing_as_owner'] = request.viewing_as_owner

    # Reason: Workforce metrics are used to inform staffing alerts.
    total_workers = Employee.objects.filter(is_active=True).count()

    new_joinees = Employee.objects.filter(
        join_date__year=current_time.year,
        join_date__month=current_time.month,
        is_active=True
    ).count()

    # Reason: Financial metrics power the dashboard summary cards.
    financials = MonthlySalary.objects.filter(month=selected_month).aggregate(
        total_gross=Coalesce(Sum('gross_pay'), Decimal('0.00')),
        total_net=Coalesce(Sum('net_pay'), Decimal('0.00')),
        total_paid=Coalesce(
            Sum('net_pay', filter=Q(is_paid=True)), Decimal('0.00')
        ),
        recovered=Coalesce(Sum('advance_deducted'), Decimal('0.00')),
    )

    # Reason: Outstanding liability highlights unpaid net payroll.
    outstanding_liability = financials['total_net'] - financials['total_paid']

    # Reason: Advance totals inform liability tracking.
    advances_given = Advance.objects.filter(
        issued_date__year=current_time.year,
        issued_date__month=current_time.month,
    ).aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total']

    # Reason: Update context in a single, consistent step.
    context.update(
        {
            'current_month': current_time,
            'total_workers': total_workers,
            'new_joinees': new_joinees,
            'financials': financials,
            'outstanding_liability': outstanding_liability,
            'advances_given': advances_given,
            'recent_activities': recent_activity_items_for_manager(limit=8),
        }
    )

    return render(request, 'portal/manager_dashboard.html', context)

@manager_required
@cache_page(60 * 5)
def manager_recent_activity_api(request):
    """Provide recent activity items for the manager dashboard.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        JsonResponse: Recent activity payload.

    Raises:
        None.

    Business Rule:
        Results are cached briefly to reduce audit-service load.
    """
    return JsonResponse(
        {'activities': recent_activity_items_for_manager(limit=8)}
    )


@manager_required
def bulk_attendance(request):
    """Bulk attendance entry for managers.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Bulk attendance page with form data.

    Raises:
        None.

    Business Rule:
        Updates are limited to current-month dates to avoid payroll drift.
    """
    # BUSINESS RULE: Bulk attendance edits are constrained to current month to protect closed payroll windows.
    today = timezone.now().date()
    
    # Reason: Date is driven by UI filters and must be constrained.
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            # Reason: Prevent edits outside the allowed payroll window.
            if selected_date > today:
                messages.warning(request, "Cannot mark attendance for future dates.")
                selected_date = today
            elif selected_date.year < today.year or (
                selected_date.year == today.year
                and selected_date.month < today.month
            ):
                messages.warning(request, "Cannot mark attendance for previous months.")
                selected_date = today
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    # Reason: POST handles writes; GET handles preview.
    if request.method == "POST":
        post_date_str = request.POST.get('attendance_date')
        try:
            selected_date = datetime.strptime(post_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            selected_date = today
        
        # Reason: Future attendance could distort payroll calculations.
        if selected_date > today:
            messages.error(request, "❌ Cannot mark attendance for future dates.")
            selected_date = today
        # Reason: Previous months may already be closed for payroll.
        elif selected_date.year < today.year or (
            selected_date.year == today.year
            and selected_date.month < today.month
        ):
            messages.error(request, "❌ Cannot mark attendance for previous months.")
            selected_date = today
        else:
            # Reason: Only valid current-month dates are persisted.
            try:
                # BACKEND LOCK: Prevent leave overrides during bulk edits.
                leave_locked_emp_ids = set(
                    Attendance.objects.filter(date=selected_date, status='L')
                    .values_list('employee_id', flat=True)
                )

                # Reason: Attendance writes must be atomic to prevent partial saves.
                with transaction.atomic():
                    # Loop through POST data to find status keys
                    for key, value in request.POST.items():
                        if key.startswith('status_'):
                            # key format: status_101 (where 101 is employee ID)
                            emp_id = key.split('_')[1]

                            # Reason: Leave-approved rows must not be overwritten.
                            if emp_id in leave_locked_emp_ids:
                                continue
                            
                            status = value
                            overtime_str = (
                                request.POST.get(f'overtime_{emp_id}', 0) or 0
                            )
                            
                            # Reason: Use Decimal to avoid float drift in payroll.
                            try:
                                overtime = Decimal(str(overtime_str)).quantize(
                                    Decimal('0.01')
                                )
                            except (ValueError, TypeError):
                                overtime = Decimal('0.00')
                            
                            Attendance.objects.update_or_create(
                                employee_id=emp_id,
                                date=selected_date,
                                defaults={
                                    'status': status,
                                    'overtime_hours': overtime,
                                }
                            )
                    
                # Reason: Build summary counts for user feedback.
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
                
                # Reason: Provide a clear confirmation summary.
                messages.success(
                    request,
                    f"✓ Attendance saved for {selected_date} | "
                    f"Present: {present} | Half Day: {half_day} | Absent: {absent}"
                )
                
            except Exception as exc:
                messages.error(request, f"Error: {exc}")

    # Reason: Always scope to active employees.
    workers = Employee.objects.filter(is_active=True).order_by('id')
    
    # Reason: Prefetch reduces per-worker queries in the loop below.
    existing_attendance = Attendance.objects.filter(date=selected_date)
    attendance_map = {att.employee_id: att for att in existing_attendance}

    worker_list = []
    for worker in workers:
        att = attendance_map.get(worker.id)
        worker_list.append({
            'employee': worker,
            # Reason: Default to present for unmarked employees.
            'status': att.status if att else 'P',
            'overtime': att.overtime_hours if att else 0,
        })

    # Reason: Dashboard cards use month-level attendance progress.
    marked_days_this_month = (
        Attendance.objects
        .filter(date__year=today.year, date__month=today.month)
        .values('date')
        .distinct()
        .count()
    )
    elapsed_days_this_month = today.day
    skipped_days_this_month = max(elapsed_days_this_month - marked_days_this_month, 0)

    context = {
        'selected_date': selected_date,
        'worker_list': worker_list,
        'today': timezone.now().date(),
        'marked_days_this_month': marked_days_this_month,
        'skipped_days_this_month': skipped_days_this_month,
    }
    
    return render(request, 'portal/bulk_attendance.html', context)


# ============================================================
# PAYROLL OPERATIONS
# ============================================================


@manager_required
def run_payroll(request):
    """
    Manager Payroll Orchestrator - PRODUCTION GRADE

    TRANSACTION GUARANTEE:
    - Entire payroll batch is wrapped in one atomic transaction.
    - Any non-skippable employee failure rolls back the whole batch.
    - Safe for monthly permanent + individual local worker salary generation.
    
    SAFETY FEATURES:
    1. Batch-level atomic transaction (all-or-nothing)
    2. Duplicate salary check (prevents re-generation)
    3. Detailed error logging for audit trail
    4. Graceful error handling with user feedback
    
    Args:
        request (HttpRequest): Incoming request.
        
    Returns:
        HttpResponse: Redirect with success/error message.

    Raises:
        ValidationError: If month selection is invalid.

    Business Rule:
        Payroll batch runs as a single transaction to avoid partial creation.
    """
    today = timezone.now().date()

    if request.method == "POST":
        logger = logging.getLogger(__name__)
        
        try:
            selected_month = datetime.strptime(
                request.POST.get('payroll_month'),
                '%Y-%m'
            ).date().replace(day=1)
            
        except (ValueError, TypeError):
            messages.error(request, "Invalid month selected.")
            return redirect('manager_dashboard')
        
        logger.info(
            f"Payroll processing started for {selected_month.strftime('%B %Y')}"
        )
        summary_url = (
            f"{reverse('payroll_batch_summary')}?month="
            f"{selected_month.strftime('%Y-%m')}"
        )
        
        employees = Employee.objects.filter(is_active=True)
        logger.info(f"Processing {employees.count()} active employees")

        created = 0
        skipped = 0
        failed = 0
        current_employee = None

        try:
            # Reason: Ensure payroll batch is all-or-nothing.
            with transaction.atomic():
                for employee in employees:
                    current_employee = employee
                    try:
                        salary = generate_monthly_salary(employee, selected_month)
                    except SalaryAlreadyGeneratedError:
                        skipped += 1
                        logger.warning(
                            f"Payroll: Salary already generated for {employee.name} "
                            f"in {selected_month.strftime('%B %Y')}"
                        )
                        continue

                    if salary is None:
                        skipped += 1
                        logger.debug(f"Skipped {employee.name} (no payable data)")
                    else:
                        created += 1
                        logger.debug(f"Salary created for {employee.name}")
        
        except Exception as e:
            # ATOMIC ROLLBACK: Any critical error rolls back ENTIRE batch
            failed = 1
            employee_name = (
                current_employee.name if current_employee else 'Unknown employee'
            )
            logger.critical(
                f"PAYROLL GENERATION ABORTED - Transaction rolled back for "
                f"{selected_month.strftime('%B %Y')} at employee {employee_name}: "
                f"{str(e)}",
                exc_info=True
            )
            messages.error(
                request,
                f"⛔ Payroll batch failed and was rolled back. "
                f"Failed employee: {employee_name}. Reason: {str(e)}"
            )
            return redirect(summary_url)

        # Success message with detailed results
        success_msg = (
            f"✅ Payroll for {selected_month.strftime('%B %Y')} completed | "
            f"Created: {created}, Skipped: {skipped}, Failed: {failed}"
        )
        logger.info(success_msg)
        
        messages.success(request, success_msg)
        
        return redirect(summary_url)

    return render(request, 'portal/run_payroll.html', {'today': today})




