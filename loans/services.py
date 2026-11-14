from django.db import transaction

from .models import Customer, LoanApplication, ScheduledRepayment, record
from .pricing import TERM_CHOICES, quote, term_label

CUSTOMER_FIELDS = [
    "title", "first_name", "last_name", "date_of_birth", "phone", "ni_number",
    "address_line1", "address_line2", "town", "county", "postcode", "years_at_address",
]
UPDATABLE_FIELDS = [
    "title", "phone", "address_line1", "address_line2", "town", "county", "postcode", "years_at_address",
]


class IdentityMismatch(Exception):
    """The email belongs to a customer with a different date of birth or NI number."""


@transaction.atomic
def create_application(data: dict, ip: str | None = None) -> LoanApplication:
    """Save a validated LoanApplicationForm's cleaned_data to the database."""
    customer, created = Customer.objects.select_for_update().get_or_create(
        email=data["email"], defaults={f: data[f] for f in CUSTOMER_FIELDS}
    )
    if not created:
        # Only let a returning customer update contact details when their
        # identity matches; otherwise anyone could overwrite another person's
        # record just by knowing their email address.
        if customer.date_of_birth != data["date_of_birth"] or customer.ni_number != data["ni_number"]:
            raise IdentityMismatch()
        for f in UPDATABLE_FIELDS:
            setattr(customer, f, data[f])
        customer.save()

    q = quote(data["amount"] * 100, TERM_CHOICES[0])
    application = LoanApplication.objects.create(
        customer=customer,
        amount_pence=q.principal_pence,
        term_months=q.term_months,
        purpose=data["purpose"],
        processing_fee_pence=q.processing_fee_pence,
        interest_pence=q.interest_pence,
        total_charges_pence=q.total_charges_pence,
        total_repayable_pence=q.total_repayable_pence,
        apr_percent=q.apr_percent,
        employment_status=data["employment_status"],
        employer_name=data.get("employer_name", ""),
        housing_status=data["housing_status"],
        monthly_income_pence=data["monthly_income"],
        monthly_housing_pence=data["monthly_housing"],
        monthly_credit_pence=data["monthly_credit"],
        monthly_other_pence=data["monthly_other"],
        account_holder_name=data["account_holder_name"],
        bank_name=data.get("bank_name", ""),
        sort_code=data["sort_code"],
        account_number=data["account_number"],
        accepted_terms=data["accepted_terms"],
        consented_credit_check=data["consented_credit_check"],
        marketing_opt_in=data.get("marketing_opt_in", False),
        submitted_ip=ip,
    )
    ScheduledRepayment.objects.bulk_create(
        ScheduledRepayment(application=application, number=i.number, due_date=i.due_date, amount_pence=i.amount_pence)
        for i in q.instalments
    )
    record(application, "submitted", f"{application.amount_display} over {term_label(application.term_months)}", actor=customer.email, ip=ip)
    return application
