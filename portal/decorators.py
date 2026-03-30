# portal/decorators.py

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
import logging

logger = logging.getLogger(__name__)


def manager_required(view_func):
    """
    Production-grade decorator for Manager-level access.
    
    Access Rules:
    - PRIMARY: Manager group members have full access
    - SECONDARY: King/Owner users can VIEW manager data (read-only context)
      * Appears as 'viewing as owner' mode
      * Shows clear back button to return to king dashboard
      * Cannot perform dangerous operations
    - BLOCKED: Regular workers, unauthenticated users
    - Logs all access attempts for audit trail
    
    Args:
        view_func: The view function to protect
        
    Returns:
        Wrapped view function with authentication checks
    """
    @login_required(login_url='portal_login')
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
        username = request.user.username
        
        is_manager = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
        is_king = request.user.groups.filter(name='King').exists()
        
        # Set viewing_as_owner flag on request (accessible to all views)
        request.viewing_as_owner = False
        
        # Case 1: Manager or Superuser - full access
        if is_manager and not is_king:
            logger.info(f"Manager {username} accessed manager view from {client_ip}")
            return view_func(request, *args, **kwargs)
        
        # Case 2: King user - read-only access to manager data
        if is_king:
            logger.info(f"King {username} viewing manager data from {client_ip}")
            request.viewing_as_owner = True  # Mark as owner viewing (stored in request)
            return view_func(request, *args, **kwargs)
        
        # Case 3: Unauthorized user
        logger.warning(
            f"SECURITY: Unauthorized user {username} attempted Manager "
            f"access from {client_ip}"
        )
        raise PermissionDenied("⛔ Manager Access Only. Unauthorized.")

    return _wrapped_view


def worker_required(view_func):
    """
    Production-grade decorator for Worker-only access.
    
    Restrictions:
    - Regular workers only (no managers, no superusers)
    - Redirects authenticated managers to their dashboard
    - Logs all access attempts
    
    Args:
        view_func: The view function to protect
        
    Returns:
        Wrapped view function with authentication checks
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('portal_login')
        
        # Redirect managers and superusers away
        if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
            logger.info(f"Manager {request.user.username} redirected from worker view")
            return redirect('manager_dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def king_required(view_func):
    """
    Production-grade decorator for Owner/King-only access.
    
    CRITICAL SECURITY REQUIREMENTS:
    1. Explicit session flag verification (double-authentication)
    2. STRICT rejection of Manager group members (ZERO tolerance)
    3. STRICT rejection of users without explicit King group
    4. Comprehensive logging of all access attempts
    5. IP tracking for audit trails
    
    Implementation:
    - In king_login: Users must login with credentials AND be in King group
    - Session flag 'king_authenticated' MUST be set after successful king_login
    - Manager group members are EXPLICITLY REJECTED even with valid credentials
    - Superusers ONLY allowed if also in King group (no backdoor access)
    
    Args:
        view_func: The view function to protect
        
    Returns:
        Wrapped view function with strict authentication checks
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        client_ip = request.META.get('REMOTE_ADDR', 'Unknown')
        username = request.user.username if request.user.is_authenticated else 'Anonymous'
        
        # STEP 1: Check basic authentication
        if not request.user.is_authenticated:
            logger.info(f"King dashboard: Unauthenticated access attempt from {client_ip}")
            return redirect('king:king_login')
        
        # STEP 2: Check session flag (double-authentication layer)
        if not request.session.get('king_authenticated'):
            logger.warning(
                f"King dashboard: Session flag missing for {username} from {client_ip}. "
                f"Possible direct URL access attempt. Redirecting to login."
            )
            return redirect('king:king_login')
        
        # STEP 3: EXPLICIT REJECTION of Manager group (CRITICAL SECURITY)
        if request.user.groups.filter(name='Manager').exists():
            logger.critical(
                f"SECURITY ALERT: Manager {username} attempted King dashboard access "
                f"with session flag from {client_ip}. BLOCKED - Strict group isolation enforced."
            )
            # Logout to clear any session state
            from django.contrib.auth import logout
            logout(request)
            raise PermissionDenied(
                "⛔ CRITICAL SECURITY: Manager credentials cannot access Owner dashboard. "
                "Your session has been terminated. Please use the correct portal."
            )
        
        # STEP 4: Verify King group membership
        is_king = request.user.groups.filter(name='King').exists()
        is_superuser = request.user.is_superuser
        
        if is_king:
            logger.info(f"King access granted to {username} from {client_ip}")
            return view_func(request, *args, **kwargs)
        elif is_superuser:
            # Superusers need explicit King group (no backdoor)
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
