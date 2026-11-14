"""Two-factor sign-in for staff.

After the password, every staff member must enter a 6-digit code from an
authenticator app (or a single-use backup code). Anyone without an app set
up is sent to the setup page first, so no staff session can reach customer
data with a password alone.
"""

import base64
from io import BytesIO
from urllib.parse import urlencode

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django_otp import devices_for_user, login as otp_login, match_token, user_has_device
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from .security import _hit, _too_many, client_ip

SETUP_SESSION_KEY = "staff_2fa_setup_device"
EXEMPT_PREFIXES = ("/staff/login/", "/staff/logout/", "/staff/2fa/")


class RequireStaffTwoFactorMiddleware:
    """Send signed-in staff who haven't entered a code to set up or verify 2FA."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            request.path.startswith("/staff/")
            and not request.path.startswith(EXEMPT_PREFIXES)
            and user is not None
            and user.is_authenticated
            and user.is_staff
            and not user.is_verified()
        ):
            target = "staff_2fa_verify" if user_has_device(user) else "staff_2fa_setup"
            return redirect(f"{reverse(target)}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)


def _next_url(request):
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return reverse("admin:index")


def _context(request, **extra):
    ctx = admin.site.each_context(request)
    ctx.update(is_nav_sidebar_enabled=False, available_apps=[], next=_next_url(request), **extra)
    return ctx


def _staff_only(view):
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return redirect(f"{reverse('staff_login')}?{urlencode({'next': request.get_full_path()})}")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def _qr_data_uri(text):
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def _make_backup_codes(user):
    StaticDevice.objects.filter(user=user).delete()
    device = StaticDevice.objects.create(user=user, name="Backup codes")
    codes = [StaticToken.random_token() for _ in range(settings.STAFF_BACKUP_CODES)]
    StaticToken.objects.bulk_create(StaticToken(device=device, token=c) for c in codes)
    return codes


def _failed_code_key(request):
    return f"rl:2fa:{request.user.pk}:{client_ip(request)}"


@never_cache
@require_http_methods(["GET", "POST"])
@_staff_only
def setup(request):
    user = request.user
    if user_has_device(user):
        # Already set up: to replace a lost phone, an admin runs `reset_staff_2fa`.
        return redirect(f"{reverse('staff_2fa_verify')}?{urlencode({'next': _next_url(request)})}")

    device = TOTPDevice.objects.filter(pk=request.session.get(SETUP_SESSION_KEY), user=user, confirmed=False).first()
    if device is None:
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()
        device = TOTPDevice.objects.create(user=user, name="Authenticator app", confirmed=False)
        request.session[SETUP_SESSION_KEY] = device.pk

    error = ""
    if request.method == "POST":
        if _hit(_failed_code_key(request), settings.LOGIN_LOCKOUT_SECONDS) > settings.LOGIN_MAX_FAILURES * 2:
            return _too_many(request, "Too many attempts. Please wait 15 minutes and try again.")
        code = "".join(request.POST.get("code", "").split())
        allowed, _ = device.verify_is_allowed()
        if not allowed:
            error = "Please wait a few seconds after a wrong code, then try the newest code from your app."
        elif code.isdigit() and device.verify_token(code):
            device.confirmed = True
            device.save()
            request.session.pop(SETUP_SESSION_KEY, None)
            cache.delete(_failed_code_key(request))
            otp_login(request, device)
            codes = _make_backup_codes(user)
            return render(request, "loans/staff_2fa_backup_codes.html", _context(request, codes=codes))
        else:
            error = "That code didn't match. Check your phone's clock is set automatically and try the newest code."

    key = base64.b32encode(device.bin_key).decode().rstrip("=")
    return render(request, "loans/staff_2fa_setup.html", _context(
        request,
        qr=_qr_data_uri(device.config_url),
        secret=" ".join(key[i:i + 4] for i in range(0, len(key), 4)),
        error=error,
    ))


@never_cache
@require_http_methods(["GET", "POST"])
@_staff_only
def verify(request):
    user = request.user
    if user.is_verified():
        return redirect(_next_url(request))
    if not user_has_device(user):
        return redirect(f"{reverse('staff_2fa_setup')}?{urlencode({'next': _next_url(request)})}")

    error = ""
    if request.method == "POST":
        if (cache.get(_failed_code_key(request)) or 0) >= settings.LOGIN_MAX_FAILURES:
            return _too_many(request, "Too many wrong codes. Please wait 15 minutes and try again.")
        code = "".join(request.POST.get("code", "").split()).lower()
        device = match_token(user, code) if code else None
        if device is not None:
            cache.delete(_failed_code_key(request))
            otp_login(request, device)
            return redirect(_next_url(request))
        _hit(_failed_code_key(request), settings.LOGIN_LOCKOUT_SECONDS)
        error = "That code didn't work. Enter the 6-digit code from your authenticator app, or one of your backup codes."

    backups_left = sum(d.token_set.count() for d in devices_for_user(user) if isinstance(d, StaticDevice))
    return render(request, "loans/staff_2fa_verify.html", _context(request, error=error, backups_left=backups_left))
