"""Emails sent to customers."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .invoice import build_invoice_pdf
from .models import record

log = logging.getLogger(__name__)


def send_application_received(application, ip=None) -> bool:
    """Email the customer to confirm we've received their application, with the invoice attached.

    A failed email never stops the application being saved: it is logged and
    written to the audit trail so staff can follow up.
    """
    customer = application.customer
    first = application.repayments.first()
    context = {
        "application": application,
        "customer": customer,
        "due_date": first.due_date if first else None,
        "lender_name": settings.LENDER_NAME,
        "lender_address": settings.LENDER_ADDRESS,
        "lender_email": settings.LENDER_EMAIL,
        "fca_number": settings.LENDER_FCA_NUMBER,
        "main_site": settings.MAIN_SITE_URL,
    }
    message = EmailMultiAlternatives(
        subject=f"We've received your application {application.reference}",
        body=render_to_string("loans/email/application_received.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer.email],
        reply_to=[settings.LENDER_EMAIL] if settings.LENDER_EMAIL else None,
    )
    message.attach_alternative(render_to_string("loans/email/application_received.html", context), "text/html")
    try:
        message.attach(f"{application.invoice_number}.pdf", build_invoice_pdf(application), "application/pdf")
        message.send()
    except Exception:
        log.exception("Confirmation email failed for %s", application.reference)
        record(application, "confirmation_email_failed", actor="system", ip=ip)
        return False
    # No address in the detail: the retention job only clears actor and IP.
    record(application, "confirmation_email_sent", actor="system", ip=ip)
    return True
