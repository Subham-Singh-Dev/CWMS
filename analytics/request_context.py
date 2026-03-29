import threading


_request_state = threading.local()


def set_current_request(request):
    _request_state.request = request


def clear_current_request():
    if hasattr(_request_state, 'request'):
        delattr(_request_state, 'request')


def get_current_request():
    return getattr(_request_state, 'request', None)


def get_current_user():
    request = get_current_request()
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        return request.user
    return None


def get_client_ip():
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
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            response = self.get_response(request)
        finally:
            clear_current_request()
        return response
