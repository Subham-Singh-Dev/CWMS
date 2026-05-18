"""Audit history views and exports.

Module: analytics.views
App: analytics
Purpose: Render audit history lists and provide CSV/PDF exports for owner and
manager scopes.
Key responsibilities: Apply role-based scoping, filter audit queries, paginate
history, and produce exports with audit trail entries.
Dependencies: analytics.models.AuditLog, audit_service, xhtml2pdf.
Author note: Managers have restricted visibility; owners see full history.
"""

# ============================================================
# IMPORTS
# ============================================================
import csv
from datetime import datetime

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import get_template
from xhtml2pdf import pisa

from analytics.models import AuditLog
from analytics.services.audit_service import create_audit_log
from portal.decorators import king_required, manager_required


def _current_filters(request):
    """Return request filter values for UI state persistence.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        dict: Current filter values to rehydrate the UI.
    """
    return {
        'activity': request.GET.get('activity', ''),
        'action': request.GET.get('action', ''),
        'username': request.GET.get('username', ''),
        'from_date': request.GET.get('from_date', ''),
        'to_date': request.GET.get('to_date', ''),
    }


def _filtered_queryset(request, is_king_view):
    """Build the filtered audit queryset for the request.

    Args:
        request (HttpRequest): Incoming request.
        is_king_view (bool): Whether to apply owner scope.

    Returns:
        QuerySet: Filtered AuditLog queryset.

    Business Rule:
        Manager scope excludes most user-auth logs except their own.
    """
    # Reason: Newest-first ordering is required for audit timeline UX.
    queryset = AuditLog.objects.all().order_by('-timestamp')
    if not is_king_view:
        queryset = _manager_scope(queryset, request)
    return _apply_audit_filters(queryset, request)


def _apply_audit_filters(queryset, request):
    """Apply querystring filters to the audit queryset.

    Args:
        queryset (QuerySet): Base audit queryset.
        request (HttpRequest): Incoming request.

    Returns:
        QuerySet: Filtered queryset.
    """
    activity = request.GET.get('activity', '').strip()
    action = request.GET.get('action', '').strip()
    username = request.GET.get('username', '').strip()
    from_date = request.GET.get('from_date', '').strip()
    to_date = request.GET.get('to_date', '').strip()

    if activity:
        queryset = queryset.filter(activity=activity)
    if action:
        queryset = queryset.filter(action=action)
    if username:
        queryset = queryset.filter(username__icontains=username)
    if from_date:
        try:
            parsed_from = datetime.strptime(from_date, '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date__gte=parsed_from)
        except ValueError:
            pass
    if to_date:
        try:
            parsed_to = datetime.strptime(to_date, '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date__lte=parsed_to)
        except ValueError:
            pass

    return queryset


def _manager_scope(queryset, request):
    """Apply manager visibility rules to audit logs.

    Args:
        queryset (QuerySet): Base audit queryset.
        request (HttpRequest): Incoming request.

    Returns:
        QuerySet: Scoped queryset for managers.

    Business Rule:
        Managers see operational logs and their own auth events.
    """
    # Managers can see operational activities + their own auth events.
    if request.user.groups.filter(name='King').exists() or request.user.is_superuser:
        return queryset
    return queryset.filter(
        ~Q(activity='user') | Q(activity='user', username=request.user.username)
    )


def _mask_ip(ip_address):
    """Mask IP address for manager views.

    Args:
        ip_address (str | None): Raw IP address.

    Returns:
        str: Masked IP address.
    """
    if not ip_address:
        return '-'
    parts = ip_address.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.***"
    return ip_address


def _serialize_logs(logs, is_king_view):
    """Serialize AuditLog rows for templates and exports.

    Args:
        logs (Iterable[AuditLog]): Audit log rows.
        is_king_view (bool): Whether full IP visibility is allowed.

    Returns:
        list[dict]: Serialized log rows.
    """
    rows = []
    for log in logs:
        rows.append({
            'timestamp': log.timestamp,
            'username': log.username,
            'user_role': log.user_role,
            'activity_display': log.get_activity_display(),
            'action_display': log.get_action_display(),
            'entity_name': log.entity_name,
            'entity_type': log.entity_type,
            'entity_id': log.entity_id,
            'details': log.details or '-',
            'status': log.status,
            'ip_address': log.ip_address if is_king_view else _mask_ip(log.ip_address),
        })
    return rows


def _render_audit_history(request, is_king_view):
    """Render audit history list with pagination.

    Args:
        request (HttpRequest): Incoming request.
        is_king_view (bool): Whether to apply owner scope.

    Returns:
        HttpResponse: Rendered audit history page.
    """
    queryset = _filtered_queryset(request, is_king_view=is_king_view)

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    log_rows = _serialize_logs(page_obj.object_list, is_king_view=is_king_view)

    return render(request, 'analytics/audit_history.html', {
        'page_obj': page_obj,
        'log_rows': log_rows,
        'is_king_view': is_king_view,
        'activities': AuditLog.ACTIVITY_CHOICES,
        'actions': AuditLog.ACTION_CHOICES,
        'current_filters': _current_filters(request),
    })


def _create_export_audit_log(request, entity_name, exported_rows):
    """Create an audit entry for export actions.

    Args:
        request (HttpRequest): Incoming request.
        entity_name (str): Export descriptor.
        exported_rows (int): Number of rows exported.
    """
    create_audit_log(
        user=request.user,
        username=request.user.username,
        activity='system',
        action='export',
        entity_type='AuditLog',
        entity_id=0,
        entity_name=entity_name,
        details=f"Exported {exported_rows} rows",
        request=request,
    )


@king_required
def king_audit_history(request):
    """Render audit history for owner scope.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Audit history page.
    """
    return _render_audit_history(request, is_king_view=True)


@manager_required
def manager_audit_history(request):
    """Render audit history for manager scope.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: Audit history page.
    """
    return _render_audit_history(request, is_king_view=False)


def _audit_csv_response(filename, queryset):
    """Return a CSV response for audit logs.

    Args:
        filename (str): Attachment filename.
        queryset (QuerySet): AuditLog queryset.

    Returns:
        HttpResponse: CSV file response.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'timestamp', 'username', 'user_role', 'activity', 'action', 'entity_type',
        'entity_id', 'entity_name', 'details', 'status', 'ip_address',
    ])

    for log in queryset:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.username,
            log.user_role,
            log.activity,
            log.action,
            log.entity_type,
            log.entity_id,
            log.entity_name,
            log.details,
            log.status,
            log.ip_address or '',
        ])

    return response


def _audit_pdf_response(filename, rows, request, is_king_view):
    """Return a PDF response for audit logs.

    Args:
        filename (str): Attachment filename.
        rows (list[dict]): Serialized audit rows.
        request (HttpRequest): Incoming request.
        is_king_view (bool): Whether full IP visibility is allowed.

    Returns:
        HttpResponse: PDF file response.
    """
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    company_name = 'Sakuntalam India Services · CWMS'

    context = {
        'company_name': company_name,
        'report_title': 'System Audit Trail',
        'generated_at': generated_at,
        'generated_by': request.user.username if request.user.is_authenticated else 'SYSTEM',
        'scope_label': (
            'Owner scope: full system visibility'
            if is_king_view
            else 'Manager scope: operational visibility'
        ),
        'rows': rows,
        'filters': {
            'activity': request.GET.get('activity', '') or 'All',
            'action': request.GET.get('action', '') or 'All',
            'username': request.GET.get('username', '') or 'All',
            'from_date': request.GET.get('from_date', '') or '-',
            'to_date': request.GET.get('to_date', '') or '-',
        },
    }

    template = get_template('analytics/audit_history_pdf.html')
    html = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Unable to generate PDF export at the moment.', status=500)
    return response


@king_required
def king_audit_export_csv(request):
    """Export owner audit history as CSV.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: CSV response.
    """
    queryset = _filtered_queryset(request, is_king_view=True)
    _create_export_audit_log(request, 'King Audit CSV Export', queryset.count())
    return _audit_csv_response('king_audit_log.csv', queryset)


@king_required
def king_audit_export_pdf(request):
    """Export owner audit history as PDF.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: PDF response.
    """
    queryset = _filtered_queryset(request, is_king_view=True)
    rows = _serialize_logs(queryset, is_king_view=True)

    _create_export_audit_log(request, 'King Audit PDF Export', len(rows))
    return _audit_pdf_response('king_audit_log.pdf', rows, request, is_king_view=True)


@manager_required
def manager_audit_export_csv(request):
    """Export manager audit history as CSV.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: CSV response.
    """
    queryset = _filtered_queryset(request, is_king_view=False)
    _create_export_audit_log(request, 'Manager Audit CSV Export', queryset.count())
    return _audit_csv_response('manager_audit_log.csv', queryset)


@manager_required
def manager_audit_export_pdf(request):
    """Export manager audit history as PDF.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: PDF response.
    """
    queryset = _filtered_queryset(request, is_king_view=False)
    rows = _serialize_logs(queryset, is_king_view=False)

    _create_export_audit_log(request, 'Manager Audit PDF Export', len(rows))
    return _audit_pdf_response('manager_audit_log.pdf', rows, request, is_king_view=False)

