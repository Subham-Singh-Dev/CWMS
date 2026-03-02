from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

def manager_required(view_func):
    """
    Security Gatekeeper:
    Allows access ONLY to:
    1. Superusers (The Owner/King)
    2. Users in the 'Manager' group

    Blocks:
    - Standard Staff (who are not Managers)
    - Workers
    - Anonymous users
    """
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        
        # 1. The Owner (King Access)
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        # 2. The Manager Group (General Access)
        if request.user.groups.filter(name='Manager').exists():
            return view_func(request, *args, **kwargs)

        # Everyone else -> BLOCK
        raise PermissionDenied("⛔ Authorized Personnel Only. Access Denied.")

    return _wrapped_view