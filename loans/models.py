import secrets
import uuid

from django.db import models
from django.utils import timezone

from .fields import EncryptedCharField
from .pricing import TERM_CHOICES, gbp


class Customer(models.Model):
    """A person who has applied. One record per email address."""

    title = models.CharField(max_length=10, blank=True)
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    date_of_birth = models.DateField()
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=16)
    ni_number = EncryptedCharField(verbose_name="National Insurance number")
    ni_last3 = models.CharField(max_length=3, editable=False, verbose_name="NI (last 3)")

    address_line1 = models.CharField(max_length=100)
    address_line2 = models.CharField(max_length=100, blank=True)
    town = models.CharField(max_length=60)
    county = models.CharField(max_length=60, blank=True)
    postcode = models.CharField(max_length=8, db_index=True)
    years_at_address = models.PositiveSmallIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def save(self, *args, **kwargs):
        self.ni_last3 = (self.ni_number or "")[-3:]
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return " ".join(p for p in (self.title, self.first_name, self.last_name) if p)

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


class LoanApplication(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        NEEDS_INFORMATION = "needs_information", "Needs information"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Purpose(models.TextChoices):
        CAR_REPAIR = "car_repair", "Car repair"
        HOME_REPAIR = "home_repair", "Home repair or appliance"
        BILLS = "bills", "Household bills"
        MEDICAL = "medical", "Medical or dental"
        TRAVEL = "travel", "Travel"
        EDUCATION = "education", "Education"
        OTHER = "other", "Other"

    class Employment(models.TextChoices):
        FULL_TIME = "full_time", "Employed full-time"
        PART_TIME = "part_time", "Employed part-time"
        SELF_EMPLOYED = "self_employed", "Self-employed"
        RETIRED = "retired", "Retired"
        STUDENT = "student", "Student"
        UNEMPLOYED = "unemployed", "Not in employment"

    class Housing(models.TextChoices):
        OWNER = "owner", "Homeowner"
        MORTGAGE = "mortgage", "Homeowner with mortgage"
        RENTING = "renting", "Renting"
        WITH_FAMILY = "with_family", "Living with family"
        OTHER = "other", "Other"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reference = models.CharField(max_length=20, unique=True, editable=False)
    invoice_number = models.CharField(max_length=24, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="applications")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True)

    # Loan requested (money stored in pence).
    amount_pence = models.PositiveIntegerField()
    term_months = models.PositiveSmallIntegerField(choices=[(t, f"{t} month{'s' if t > 1 else ''}") for t in TERM_CHOICES])
    purpose = models.CharField(max_length=20, choices=Purpose.choices)

    # Pricing frozen at submission time, so later rate changes cannot alter it.
    processing_fee_pence = models.PositiveIntegerField()
    interest_pence = models.PositiveIntegerField()
    total_charges_pence = models.PositiveIntegerField()
    total_repayable_pence = models.PositiveIntegerField()
    apr_percent = models.DecimalField(max_digits=8, decimal_places=1)

    # Employment and affordability (monthly figures, pence).
    employment_status = models.CharField(max_length=20, choices=Employment.choices)
    employer_name = models.CharField(max_length=100, blank=True)
    housing_status = models.CharField(max_length=20, choices=Housing.choices)
    monthly_income_pence = models.PositiveIntegerField()
    monthly_housing_pence = models.PositiveIntegerField()
    monthly_credit_pence = models.PositiveIntegerField()
    monthly_other_pence = models.PositiveIntegerField()

    # UK bank account for paying out the loan and collecting repayments.
    account_holder_name = models.CharField(max_length=70)
    bank_name = models.CharField(max_length=70, blank=True)
    sort_code = models.CharField(max_length=8)
    account_number = EncryptedCharField()
    account_last4 = models.CharField(max_length=4, editable=False, verbose_name="Account (last 4)")

    # Consents.
    accepted_terms = models.BooleanField(default=False)
    consented_credit_check = models.BooleanField(default=False)
    marketing_opt_in = models.BooleanField(default=False)

    submitted_ip = models.GenericIPAddressField(null=True, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]

    def save(self, *args, **kwargs):
        self.account_last4 = (self.account_number or "")[-4:]
        if not self.reference:
            self.reference = self._unique_code("SWL", "reference")
        if not self.invoice_number:
            self.invoice_number = self._unique_code(f"INV-{timezone.now():%Y%m}", "invoice_number")
        super().save(*args, **kwargs)

    @classmethod
    def _unique_code(cls, prefix, field):
        while True:
            code = f"{prefix}-{secrets.token_hex(4).upper()}"
            if not cls.objects.filter(**{field: code}).exists():
                return code

    @property
    def monthly_outgoings_pence(self):
        return self.monthly_housing_pence + self.monthly_credit_pence + self.monthly_other_pence

    @property
    def disposable_income_pence(self):
        return self.monthly_income_pence - self.monthly_outgoings_pence

    @property
    def largest_instalment_pence(self):
        return max((i.amount_pence for i in self.repayments.all()), default=0)

    @property
    def amount_display(self):
        return gbp(self.amount_pence)

    def __str__(self):
        return f"{self.reference} – {gbp(self.amount_pence)} over {self.term_months}m"


class ScheduledRepayment(models.Model):
    application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name="repayments")
    number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount_pence = models.PositiveIntegerField()

    class Meta:
        ordering = ["application", "number"]
        constraints = [models.UniqueConstraint(fields=["application", "number"], name="unique_instalment_number")]

    def __str__(self):
        return f"{self.application.reference} #{self.number} {gbp(self.amount_pence)} due {self.due_date}"


class AuditEvent(models.Model):
    """Append-only record of what happened to an application."""

    application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name="audit_events")
    action = models.CharField(max_length=40)
    detail = models.CharField(max_length=255, blank=True)
    actor = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"


def record(application, action, detail="", actor="", ip=None):
    return AuditEvent.objects.create(application=application, action=action, detail=detail[:255], actor=actor, ip_address=ip)
