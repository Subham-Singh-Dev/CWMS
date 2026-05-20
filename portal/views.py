"""Portal view handlers.

Module: portal.views
App: portal
Purpose: Handles login, worker/manager dashboards, and payroll orchestration.
Key responsibilities: Role-based access control, payroll batching, attendance
bulk operations, and audit logging for portal interactions.
Dependencies: employees, attendance, payroll, audit service, and decorators.
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
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from xhtml2pdf import pisa

from analytics.services.audit_service import create_audit_log, recent_activity_items_for_manager
from attendance.models import Attendance
from employees.models import Employee
from payroll.models import Advance, MonthlySalary
from leaves.models import LeaveAllocation, LeaveRecord
from payroll.services import SalaryAlreadyGeneratedError, generate_monthly_salary

from .decorators import manager_required, worker_required


def _cache_delete_pattern(pattern: str) -> None:
    from config.cache_utils import delete_pattern as _delete_pattern
    try:
        _delete_pattern(pattern)
    except Exception:
        pass

# ============================================================
# WORKER PORTAL VIEWS
# ============================================================

def portal_login(request):
    """Authenticate manager/worker based on selected login mode."""
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
            return redirect('manager_dashboard')
        return redirect('worker_dashboard')

    if request.method == "POST":
        login_id = request.POST.get('login_id', '').strip()
        password = request.POST.get('password', '')
        login_type = request.POST.get('login_type', 'worker')

        user = None

        if login_type == 'manager':
            user = authenticate(request, username=login_id, password=password)
        else:
            try:
                employee = Employee.objects.get(phone_number=login_id, is_active=True)
                user = authenticate(
                    request,
                    username=employee.user.username,
                    password=password,
                )
            except Employee.DoesNotExist:
                pass

        if user is not None and user.is_active:
            is_manager = user.is_superuser or user.groups.filter(name='Manager').exists()

            if login_type == 'manager' and not is_manager:
                messages.error(request, "Invalid credentials or unauthorized role.")
            elif login_type == 'worker' and is_manager:
                messages.error(request, "Managers must use the Manager login tab.")
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
    """Render worker-scoped dashboard with salary, attendance, leaves, and advances."""
    try:
        employee = request.user.employee
        if not employee.is_active:
            raise Employee.DoesNotExist
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')

    today = timezone.now().date()

    # 1. SALARY & PAYSLIPS
    salaries = MonthlySalary.objects.filter(employee=employee).order_by('-month')
    current_salary = salaries.first()

    # 2. ATTENDANCE (Current Month)
    current_month_attendances = Attendance.objects.filter(
        employee=employee,
        date__year=today.year,
        date__month=today.month
    )

    calendar_entries = [
        {'day': att.date.day, 'status': att.status}
        for att in current_month_attendances
    ]

    att_present = current_month_attendances.filter(status='P').count()
    att_half = current_month_attendances.filter(status='H').count()
    att_absent = current_month_attendances.filter(status='A').count()
    att_leave = current_month_attendances.filter(status='L').count()

    # 3. LEAVE BALANCES (Current Year)
    current_year = today.year
    allocation = LeaveAllocation.objects.filter(employee=employee, year=current_year).first()

    leave_records = LeaveRecord.objects.filter(
        employee=employee,
        from_date__year=current_year,
        status='approved'
    )

    used_el = sum(r.total_days for r in leave_records if r.leave_type == 'EL')
    used_cl = sum(r.total_days for r in leave_records if r.leave_type == 'CL')
    used_sl = sum(r.total_days for r in leave_records if r.leave_type == 'SL')

    total_days = allocation.total_days if allocation else 0
    leave_cl_total = min(8, total_days) if total_days > 0 else 0
    leave_sl_total = min(7, max(total_days - 8, 0)) if total_days > 0 else 0
    leave_el_total = max(total_days - 15, 0) if total_days > 0 else 0

    leave_el_remaining = max(leave_el_total - used_el, 0)
    leave_cl_remaining = max(leave_cl_total - used_cl, 0)
    leave_sl_remaining = max(leave_sl_total - used_sl, 0)

    def calc_pct(used, total):
        return int((used / total) * 100) if total > 0 else 0

    # 4. ADVANCES & RECOVERIES
    advances = Advance.objects.filter(employee=employee).order_by('-issued_date')
    
    total_advanced = advances.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total']
    
    total_recovered = salaries.aggregate(
        total=Coalesce(Sum('advance_deducted'), Decimal('0.00'))
    )['total']
    
    outstanding_advance = max(total_advanced - total_recovered, Decimal('0.00'))

    # CONTEXT ASSEMBLY
    context = {
        'employee': employee,
        'salaries': salaries,
        'current_salary': current_salary,
        'current_month_label': today.strftime("%B %Y"),
        'att_present': att_present,
        'att_half': att_half,
        'att_absent': att_absent,
        'att_leave': att_leave,
        'calendar_entries': calendar_entries,
        'cal_year': today.year,
        'cal_month_0indexed': today.month - 1,
        'leave_el_remaining': leave_el_remaining,
        'leave_el_total': leave_el_total,
        'leave_el_pct': calc_pct(used_el, leave_el_total),
        'leave_cl_remaining': leave_cl_remaining,
        'leave_cl_total': leave_cl_total,
        'leave_cl_pct': calc_pct(used_cl, leave_cl_total),
        'leave_sl_remaining': leave_sl_remaining,
        'leave_sl_total': leave_sl_total,
        'leave_sl_pct': calc_pct(used_sl, leave_sl_total),
        'advances': advances,
        'outstanding_advance': outstanding_advance,
    }

    return render(request, 'portal/worker_dashboard.html', context)


def worker_logout(request):
    """Logout worker/manager sessions and record the event in audit trail."""
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
    """Render worker profile page."""
    try:
        employee = request.user.employee
    except Employee.DoesNotExist:
        logout(request)
        return redirect('portal_login')
    return render(request, 'portal/worker_profile.html', {'employee': employee})


@worker_required
def download_payslip(request, salary_id):
    """Download paid payslip with ownership enforcement for worker accounts."""
    salary = get_object_or_404(
        MonthlySalary.objects.select_related('employee'),
        id=salary_id,
    )

    is_manager = request.user.groups.filter(name='Manager').exists()

    if request.user.is_superuser or is_manager:
        pass
    elif hasattr(request.user, 'employee'):
        if salary.employee != request.user.employee:
            raise PermissionDenied('⛔ You are not authorized to view this payslip.')
        if not salary.is_paid:
            raise PermissionDenied("⏳ Payslip not available until salary is paid.")
    else:
        raise PermissionDenied("Unauthorized access.")

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

# ============================================================
# MANAGER PORTAL VIEWS
# ============================================================

@manager_required
def manager_dashboard(request, viewing_as_owner=False):
    """Production-grade Manager Dashboard View."""
    context = {}

    current_time = timezone.now()
    today = current_time.date()
    selected_month = today.replace(day=1)

    context['selected_month'] = selected_month.strftime('%Y-%m')

    cache_key = (
        f"dashboard:manager:{request.user.id}:"
        f"{context['selected_month']}:"
        f"{request.session.session_key or 'anon'}"
    )
    cached_html = cache.get(cache_key)
    if cached_html:
        return HttpResponse(cached_html)
    
    month_date = datetime.strptime(
        context['selected_month'], '%Y-%m'
    ).date().replace(day=1)

    payroll_exists = MonthlySalary.objects.filter(month=month_date).exists()
    context['payroll_exists'] = payroll_exists
    context['viewing_as_owner'] = getattr(request, 'viewing_as_owner', False)

    total_workers = Employee.objects.filter(is_active=True).count()
    new_joinees = Employee.objects.filter(
        join_date__year=current_time.year,
        join_date__month=current_time.month,
        is_active=True
    ).count()

    financials = MonthlySalary.objects.filter(month=selected_month).aggregate(
        total_gross=Coalesce(Sum('gross_pay'), Decimal('0.00')),
        total_net=Coalesce(Sum('net_pay'), Decimal('0.00')),
        total_paid=Coalesce(
            Sum('net_pay', filter=Q(is_paid=True)), Decimal('0.00')
        ),
        recovered=Coalesce(Sum('advance_deducted'), Decimal('0.00')),
    )

    outstanding_liability = financials['total_net'] - financials['total_paid']

    advances_given = Advance.objects.filter(
        issued_date__year=current_time.year,
        issued_date__month=current_time.month,
    ).aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total']

    activity_cache_key = f"activity:manager:{request.user.id}"
    recent_activities = cache.get(activity_cache_key)
    if recent_activities is None:
        recent_activities = recent_activity_items_for_manager(limit=8)
        cache.set(activity_cache_key, recent_activities, timeout=300)

    context.update(
        {
            'current_month': current_time,
            'total_workers': total_workers,
            'new_joinees': new_joinees,
            'financials': financials,
            'outstanding_liability': outstanding_liability,
            'advances_given': advances_given,
            'recent_activities': recent_activities,
        }
    )

    html = render_to_string('portal/manager_dashboard.html', context, request=request)
    cache.set(cache_key, html, timeout=300)
    return HttpResponse(html)


@manager_required
def manager_recent_activity_api(request):
    """Provide recent activity items for the manager dashboard."""
    cache_key = f"activity:manager:{request.user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({'activities': cached, 'cached': True})

    activities = recent_activity_items_for_manager(limit=8)
    cache.set(cache_key, activities, timeout=300)
    return JsonResponse({'activities': activities, 'cached': False})


@manager_required
def bulk_attendance(request):
    """Bulk attendance entry for managers."""
    today = timezone.now().date()
    
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
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

    if request.method == "POST":
        post_date_str = request.POST.get('attendance_date')
        try:
            selected_date = datetime.strptime(post_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            selected_date = today
        
        if selected_date > today:
            messages.error(request, "❌ Cannot mark attendance for future dates.")
            selected_date = today
        elif selected_date.year < today.year or (
            selected_date.year == today.year
            and selected_date.month < today.month
        ):
            messages.error(request, "❌ Cannot mark attendance for previous months.")
            selected_date = today
        else:
            try:
                leave_locked_emp_ids = set(
                    Attendance.objects.filter(date=selected_date, status='L')
                    .values_list('employee_id', flat=True)
                )

                with transaction.atomic():
                    for key, value in request.POST.items():
                        if key.startswith('status_'):
                            emp_id = key.split('_')[1]

                            if int(emp_id) in leave_locked_emp_ids:
                                continue
                            
                            status = value
                            overtime_str = request.POST.get(f'overtime_{emp_id}', 0) or 0
                            
                            try:
                                overtime = Decimal(str(overtime_str)).quantize(Decimal('0.01'))
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
                
                messages.success(
                    request,
                    f"✓ Attendance saved for {selected_date} | "
                    f"Present: {present} | Half Day: {half_day} | Absent: {absent}"
                )

                from config.cache_utils import delete_patterns
                delete_patterns([
                    "api:attendance:*",
                    "dashboard:manager:*",
                    "dashboard:king:*",
                ])
                
            except Exception as exc:
                messages.error(request, f"Error: {exc}")

    workers = Employee.objects.filter(is_active=True).order_by('id')
    
    existing_attendance = Attendance.objects.filter(date=selected_date)
    attendance_map = {att.employee_id: att for att in existing_attendance}

    worker_list = []
    for worker in workers:
        att = attendance_map.get(worker.id)
        worker_list.append({
            'employee': worker,
            'status': att.status if att else 'P',
            'overtime': att.overtime_hours if att else 0,
        })

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
    """Manager Payroll Orchestrator."""
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
        
        logger.info(f"Payroll processing started for {selected_month.strftime('%B %Y')}")
        summary_url = f"{reverse('payroll_batch_summary')}?month={selected_month.strftime('%Y-%m')}"
        
        employees = Employee.objects.filter(is_active=True)
        logger.info(f"Processing {employees.count()} active employees")

        created = 0
        skipped = 0
        failed = 0
        current_employee = None

        try:
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
            failed = 1
            employee_name = current_employee.name if current_employee else 'Unknown employee'
            logger.critical(
                f"PAYROLL GENERATION ABORTED - Transaction rolled back for "
                f"{selected_month.strftime('%B %Y')} at employee {employee_name}: {str(e)}",
                exc_info=True
            )
            messages.error(
                request,
                f"⛔ Payroll batch failed and was rolled back. "
                f"Failed employee: {employee_name}. Reason: {str(e)}"
            )
            return redirect(summary_url)

        success_msg = (
            f"✅ Payroll for {selected_month.strftime('%B %Y')} completed | "
            f"Created: {created}, Skipped: {skipped}, Failed: {failed}"
        )
        logger.info(success_msg)
        
        messages.success(request, success_msg)
        
        return redirect(summary_url)

    return render(request, 'portal/run_payroll.html', {'today': today})