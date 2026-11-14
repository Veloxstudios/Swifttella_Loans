"""Launch checks for customer email, shown by `manage.py check --deploy`."""

from email.utils import parseaddr

from django.conf import settings
from django.core.checks import Warning, register


@register("email", deploy=True)
def email_is_ready(app_configs, **kwargs):
    problems = []
    if not settings.EMAIL_IS_CONFIGURED:
        problems.append(Warning(
            "No email provider is set up, so customers won't get confirmation emails.",
            hint="Set EMAIL_DOMAIN, EMAIL_PROVIDER and EMAIL_API_KEY. See EMAIL_SETUP.md.",
            id="loans.E001",
        ))
    if settings.EMAIL_PROVIDER and settings.EMAIL_PROVIDER not in {"postmark", "resend", "brevo", "mailgun", "sendgrid", "smtp"}:
        problems.append(Warning(
            f"EMAIL_PROVIDER={settings.EMAIL_PROVIDER!r} isn't supported.",
            hint="Use postmark, resend, brevo, mailgun, sendgrid or smtp.",
            id="loans.E002",
        ))
    if not settings.EMAIL_DOMAIN:
        problems.append(Warning(
            "EMAIL_DOMAIN isn't set, so emails would come from no-reply@localhost.",
            hint="Set EMAIL_DOMAIN to the domain you verified with your email provider.",
            id="loans.E003",
        ))
    else:
        sender_domain = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2].lower()
        if sender_domain != settings.EMAIL_DOMAIN and not sender_domain.endswith("." + settings.EMAIL_DOMAIN):
            problems.append(Warning(
                f"Emails are sent from {sender_domain}, not your domain {settings.EMAIL_DOMAIN}. "
                "They will fail SPF/DKIM/DMARC checks and land in spam.",
                hint="Remove DEFAULT_FROM_EMAIL, or set it to an address on EMAIL_DOMAIN.",
                id="loans.E004",
            ))
    return problems
