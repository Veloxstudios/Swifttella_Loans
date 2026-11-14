"""Remove a staff member's authenticator app and backup codes, e.g. after a lost phone.

    python manage.py reset_staff_2fa <username>

They set up a new app the next time they sign in. Check who is asking before
running this: anyone who can reset 2FA can take over the account.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = "Remove a staff member's two-factor devices so they can set up a new authenticator app."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        try:
            user = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist as exc:
            raise CommandError(f"No user called {username!r}.") from exc
        TOTPDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Reset two-factor sign-in for {username}. They will set up a new authenticator app at their next sign-in."))
