"""Send a test email to check your domain and email provider are set up.

    python manage.py send_test_email you@example.com
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email through the configured provider."

    def add_arguments(self, parser):
        parser.add_argument("to")

    def handle(self, *args, to, **options):
        self.stdout.write(f"Provider: {settings.EMAIL_PROVIDER or '(none)'}  ->  {settings.EMAIL_BACKEND}")
        self.stdout.write(f"From:     {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Reply-To: {settings.LENDER_EMAIL or '(none)'}")
        if not settings.EMAIL_IS_CONFIGURED:
            self.stdout.write(self.style.WARNING(
                "No email provider is set up, so this email will not be delivered. See EMAIL_SETUP.md."))
        message = EmailMessage(
            subject=f"{settings.LENDER_NAME} test email",
            body=(
                f"This is a test email from {settings.LENDER_NAME}.\n\n"
                "If it arrived in your inbox (not spam), your domain and email provider are set up correctly.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
            reply_to=[settings.LENDER_EMAIL] if settings.LENDER_EMAIL else None,
        )
        try:
            message.send()
        except Exception as exc:
            raise CommandError(f"Sending failed: {exc}") from exc
        status = getattr(message, "anymail_status", None)
        if status is not None:
            self.stdout.write(f"Provider status: {status.status}  message id: {status.message_id}")
        self.stdout.write(self.style.SUCCESS(f"Sent to {to}. Check the inbox and the spam folder."))
