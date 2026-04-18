"""
Module: analytics.request_context
App: analytics
Purpose: Thread-local request context helpers so model signals/services can access current user/IP.
Dependencies: threading local storage.
Author note: Context is always cleared in middleware finally block to avoid cross-request leakage.
"""

import threading


_request_state = threading.local()


def set_current_request(request):
    """Store current request in thread-local state for downstream access."""
    _request_state.request = request


def clear_current_request():
    """Remove thread-local request reference after response lifecycle ends."""
    if hasattr(_request_state, 'request'):
        delattr(_request_state, 'request')


def get_current_request():
    """Return current thread-local request if present, else None."""
    return getattr(_request_state, 'request', None)


def get_current_user():
    """Return authenticated user from current request when available."""
    request = get_current_request()
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        return request.user
    return None


def get_client_ip():
    """Resolve client IP from forwarded header fallback to remote address."""
    request = get_current_request()
    if not request:
        return None

    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class CurrentRequestMiddleware:
    """Store current request in thread local so signals can access user/IP."""

    def __init__(self, get_response):
        """Capture next middleware callable in chain."""
        self.get_response = get_response

    def __call__(self, request):
        """Populate and clear thread-local request around downstream execution."""
        set_current_request(request)
        try:
            response = self.get_response(request)
        finally:
            clear_current_request()
        return response
