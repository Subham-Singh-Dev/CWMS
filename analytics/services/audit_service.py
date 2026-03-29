from analytics.models import AuditLog


def infer_user_role(user):
    if not user or not user.is_authenticated:
        return 'System'
    if user.groups.filter(name='King').exists() or user.is_superuser:
        return 'King'
    if user.groups.filter(name='Manager').exists():
        return 'Manager'
    return 'Worker'


def create_audit_log(
    *,
    user,
    username,
    activity,
    action,
    entity_type,
    entity_id,
    entity_name,
    details='',
    status='success',
    error_message='',
    request=None,
):
    ip_address = None
    if request is not None:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            ip_address = forwarded.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

    return AuditLog.objects.create(
        user=user,
        username=username or 'SYSTEM',
        user_role=infer_user_role(user),
        activity=activity,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        details=details,
        ip_address=ip_address,
        status=status,
        error_message=error_message,
    )


def to_activity_item(log):
    icon_map = {
        'attendance': '👤',
        'payroll': '💵',
        'expense': '💸',
        'bill': '📄',
        'employee': '🧑‍🔧',
        'workorder': '🧾',
        'revenue': '📈',
        'user': '🔐',
        'system': 'ℹ️',
    }
    type_map = {
        'attendance': 'info',
        'payroll': 'success',
        'expense': 'warning',
        'bill': 'info',
        'employee': 'info',
        'workorder': 'info',
        'revenue': 'success',
        'user': 'info',
        'system': 'info',
    }

    action = (log.get_action_display() if hasattr(log, 'get_action_display') else log.action).lower()
    return {
        'icon': icon_map.get(log.activity, 'ℹ️'),
        'type': type_map.get(log.activity, 'info'),
        'text': f"{log.entity_name or log.entity_type} — {action} by {log.username}",
        'time': log.timestamp.strftime('%Y-%m-%d %H:%M'),
    }


def recent_activity_items_for_king(limit=8):
    logs = AuditLog.objects.order_by('-timestamp')[:limit]
    return [to_activity_item(log) for log in logs]


def recent_activity_items_for_manager(limit=8):
    logs = AuditLog.objects.exclude(activity='user').order_by('-timestamp')[:limit]
    return [to_activity_item(log) for log in logs]
