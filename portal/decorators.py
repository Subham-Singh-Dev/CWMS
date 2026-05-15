"""Portal access-control decorators.

Module: portal.decorators
App: portal
Purpose: Centralizes role-based access gates for manager, worker, and king routes.
Key responsibilities: Enforce role isolation, session checks, and audit logging
before protected view logic runs.
Dependencies: Django auth/session, group membership via auth groups.
Author note: These decorators are intentionally strict to prevent privilege bleed
across Manager/Worker/King boundaries.
"""

# ============================================================
# IMPORTS
# ============================================================
import logging
from functools import wraps

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


 # ============================================================
 # MANAGER ACCESS
 # ============================================================
def manager_required(view_func):
    """Protect manager routes and allow owner read-only access.

    Args:
        view_func (Callable): View function to protect.

    Returns:
        Callable: Wrapped view function with access checks enforced.

    Raises:
        PermissionDenied: When the caller is not authorized.

    Business Rule:
        King users may view manager data in read-only mode but cannot act.
    """
    @login_required(login_url='portal_login')
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        """Authorize manager routes and optionally enable owner read-only viewing mode."""
        client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
        username = request.user.username
        
        # Reason: Group checks are centralized to keep permissions consistent.
        is_manager = (
            request.user.is_superuser
            or request.user.groups.filter(name='Manager').exists()
        )
        is_king = request.user.groups.filter(name='King').exists()

        # Reason: Flag drives UI behavior without granting permissions.
        request.viewing_as_owner = False
        
        # Reason: Managers must have full operational access.
        if is_manager and not is_king:
            logger.info(f"Manager {username} accessed manager view from {client_ip}")
            return view_func(request, *args, **kwargs)
        
        # Reason: King access is read-only and explicitly tracked.
        if is_king:
            logger.info(f"King {username} viewing manager data from {client_ip}")
            request.viewing_as_owner = True
            return view_func(request, *args, **kwargs)
        
        # Reason: Unauthorized access is blocked and logged for audit trails.
        logger.warning(
            f"SECURITY: Unauthorized user {username} attempted Manager "
            f"access from {client_ip}"
        )
        raise PermissionDenied("⛔ Manager Access Only. Unauthorized.")

    return _wrapped_view


 # ============================================================
 # WORKER ACCESS
 # ============================================================
def worker_required(view_func):
    """Protect worker-only routes.

    Args:
        view_func (Callable): View function to protect.

    Returns:
        Callable: Wrapped view function with access checks enforced.

    Raises:
        None.

    Business Rule:
        Managers and superusers must not access worker-only views.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Allow worker-only access and redirect manager/superuser users away."""
        # Reason: Anonymous access should route through login.
        if not request.user.is_authenticated:
            return redirect('portal_login')

        # Reason: Prevent manager users from viewing worker-only data.
        if request.user.is_superuser or request.user.groups.filter(
            name='Manager'
        ).exists():
            logger.info(f"Manager {request.user.username} redirected from worker view")
            return redirect('manager_dashboard')

        return view_func(request, *args, **kwargs)

    return wrapper


 # ============================================================
 # KING ACCESS
 # ============================================================
def king_required(view_func):
    """Protect king-only routes with strict session and group checks.

    Args:
        view_func (Callable): View function to protect.

    Returns:
        Callable: Wrapped view function with strict access checks enforced.

    Raises:
        PermissionDenied: When the caller fails king authorization checks.

    Business Rule:
        King access requires explicit King group membership and a valid
        king_authenticated session flag.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Enforce strict king session and group membership before protected view access."""
        client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
        username = request.user.username if request.user.is_authenticated else 'Anonymous'
        
        # Reason: Block unauthenticated access to king-only routes.
        if not request.user.is_authenticated:
            logger.info(f"King dashboard: Unauthenticated access attempt from {client_ip}")
            return redirect('king:king_login')

        # Reason: Enforce the secondary login confirmation flag.
        if not request.session.get('king_authenticated'):
            logger.warning(
                f"King dashboard: Session flag missing for {username} from {client_ip}. "
                f"Possible direct URL access attempt. Redirecting to login."
            )
            return redirect('king:king_login')

        # Reason: Manager credentials must never access owner routes.
        if request.user.groups.filter(name='Manager').exists():
            logger.critical(
                f"SECURITY ALERT: Manager {username} attempted King dashboard access "
                f"with session flag from {client_ip}. BLOCKED - Strict group isolation enforced."
            )
            logout(request)
            raise PermissionDenied(
                "⛔ CRITICAL SECURITY: Manager credentials cannot access Owner dashboard. "
                "Your session has been terminated. Please use the correct portal."
            )

        # Reason: Only explicit King group members may proceed.
        is_king = request.user.groups.filter(name='King').exists()
        is_superuser = request.user.is_superuser

        if is_king:
            logger.info(f"King access granted to {username} from {client_ip}")
            return view_func(request, *args, **kwargs)
        elif is_superuser:
            # Reason: Prevent superuser backdoor into king routes.
            logger.critical(
                f"SECURITY: Superuser {username} attempted King access without King group "
                f"from {client_ip}. BLOCKED - Explicit King group required."
            )
            raise PermissionDenied(
                "⛔ Owner Access Only. Superuser requires explicit King group membership."
            )
        else:
            logger.warning(
                f"SECURITY: {username} with session flag but no King group attempted "
                f"access from {client_ip}. BLOCKED."
            )
            raise PermissionDenied("⛔ Owner Access Only. Unauthorized.")

    return wrapper
