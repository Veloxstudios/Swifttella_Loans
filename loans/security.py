"""Security headers and simple, shared rate limits.

Rate limit counters live in the Django cache. In production the cache is the
database (see CACHES in settings), so every gunicorn worker sees the same counts.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.signals import user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.http import HttpResponse

# Only our own files may load. No inline scripts, no third-party scripts, no framing.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        # Pages with personal data must not be kept by browsers or proxies.
        if request.path.startswith(("/staff/", "/application/")) or request.method == "POST":
            response["Cache-Control"] = "no-store"
        return response


def client_ip(request):
    """The visitor's IP address, as seen by our own proxy.

    A visitor can put anything in X-Forwarded-For, and each proxy appends the
    address it saw. So we count TRUSTED_PROXIES entries in from the right
    (Railway adds one), never trusting the left-most, visitor-supplied value.
    """
    hops = settings.TRUSTED_PROXIES
    forwarded = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    if hops and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.META.get("REMOTE_ADDR") or "unknown"


def _hit(key, window):
    """Add one to a counter that expires `window` seconds after it was first set."""
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # expired between add() and incr()
        cache.set(key, 1, window)
        return 1


def _too_many(request, message):
    response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
    response["Retry-After"] = "900"
    return response


def limit_submissions(view):
    """Stop one address flooding the application form."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method == "POST":
            count = _hit(f"rl:apply:{client_ip(request)}", settings.APPLY_RATE_WINDOW)
            if count > settings.APPLY_RATE_LIMIT:
                return _too_many(request, "Too many applications have been sent from your connection. Please try again later.")
        return view(request, *args, **kwargs)

    return wrapper


# ---------- Staff sign-in lockout ----------

def _login_keys(request, username):
    ip = client_ip(request)
    return f"rl:login:ip:{ip}", f"rl:login:user:{(username or '').lower()}"


@receiver(user_login_failed)
def _count_failed_login(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    for key in _login_keys(request, credentials.get("username")):
        _hit(key, settings.LOGIN_LOCKOUT_SECONDS)


def is_locked_out(request, username):
    return any((cache.get(k) or 0) >= settings.LOGIN_MAX_FAILURES for k in _login_keys(request, username))


def clear_failures(request, username):
    cache.delete_many(list(_login_keys(request, username)))


def guarded_login(login_view):
    """Wrap the staff login: lock an IP or username out after repeated failures."""

    @wraps(login_view)
    def wrapper(request, *args, **kwargs):
        username = request.POST.get("username", "") if request.method == "POST" else ""
        if request.method == "POST" and is_locked_out(request, username):
            return _too_many(request, "Too many failed sign-in attempts. Please wait 15 minutes and try again.")
        response = login_view(request, *args, **kwargs)
        if request.method == "POST" and request.user.is_authenticated:
            clear_failures(request, username)
        return response

    return wrapper
