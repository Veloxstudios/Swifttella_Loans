"""Remove personal data from applications that never became a loan (UK GDPR storage limitation).

Run it daily, for example as a Railway cron job:

    python manage.py anonymise_old_applications --apply

Without --apply it only reports what it would do. Approved applications are
left alone: once a loan is made, records must be kept for as long as the
law and the FCA require, and those rules need their own process.
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from loans.models import Customer, LoanApplication, record

REMOVED = "[removed]"


def anonymise_application(app):
    app.account_holder_name = REMOVED
    app.bank_name = ""
    app.sort_code = "00-00-00"
    app.account_number = ""
    app.employer_name = ""
    app.submitted_ip = None
    app.personal_data_removed_at = timezone.now()
    app.save()
    # Strip personal details from the audit trail too, but keep what happened and when.
    app.audit_events.update(actor="", ip_address=None)
    record(app, "personal_data_removed", "Retention period ended", actor="retention process")


def anonymise_customer(customer):
    customer.title = ""
    customer.first_name = REMOVED
    customer.last_name = ""
    customer.date_of_birth = date(1900, 1, 1)
    customer.email = f"removed-{customer.pk}@invalid.example"
    customer.phone = ""
    customer.ni_number = ""
    customer.address_line1 = REMOVED
    customer.address_line2 = ""
    customer.town = ""
    customer.county = ""
    customer.postcode = ""
    customer.years_at_address = 0
    customer.personal_data_removed_at = timezone.now()
    customer.save()


class Command(BaseCommand):
    help = "Remove personal data from applications that did not become a loan once the retention period ends."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Make the changes. Without this, only report.")
        parser.add_argument("--days", type=int, default=settings.DATA_RETENTION_DAYS,
                            help=f"Retention period in days (default {settings.DATA_RETENTION_DAYS}).")

    def handle(self, *args, apply=False, days=None, **options):
        cutoff = timezone.now() - timedelta(days=days)
        due = (LoanApplication.objects
               .filter(submitted_at__lt=cutoff, personal_data_removed_at__isnull=True)
               .exclude(status=LoanApplication.Status.APPROVED)
               .select_related("customer"))
        apps = list(due)
        self.stdout.write(f"{len(apps)} application(s) older than {days} days are due for personal data removal.")
        if not apply:
            self.stdout.write("Dry run: nothing changed. Add --apply to remove the data.")
            return

        customers = set()
        with transaction.atomic():
            for app in apps:
                anonymise_application(app)
                customers.add(app.customer_id)
            removed_customers = 0
            for customer in Customer.objects.filter(pk__in=customers, personal_data_removed_at__isnull=True):
                # Keep the person's details while any of their applications still needs them.
                if not customer.applications.filter(personal_data_removed_at__isnull=True).exists():
                    anonymise_customer(customer)
                    removed_customers += 1
        self.stdout.write(self.style.SUCCESS(
            f"Removed personal data from {len(apps)} application(s) and {removed_customers} customer record(s)."))
