from decimal import Decimal, InvalidOperation

from django import forms

from . import validators as v
from .models import LoanApplication
from .pricing import MAX_AMOUNT_GBP, MIN_AMOUNT_GBP, TERM_CHOICES

TITLE_CHOICES = [("", "—"), ("Mr", "Mr"), ("Mrs", "Mrs"), ("Miss", "Miss"), ("Ms", "Ms"), ("Mx", "Mx"), ("Dr", "Dr")]


class MoneyField(forms.DecimalField):
    """Pounds-and-pence input that cleans to an integer number of pence."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("min_value", Decimal("0"))
        kwargs.setdefault("widget", forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}))
        super().__init__(*args, **kwargs)

    def clean(self, value):
        pounds = super().clean(value)
        if pounds is None:
            return None
        try:
            return int((pounds * 100).to_integral_value())
        except InvalidOperation as exc:
            raise forms.ValidationError("Enter an amount in pounds.") from exc


class LoanApplicationForm(forms.Form):
    # Loan
    amount = forms.IntegerField(
        label="How much would you like to borrow? (£)",
        min_value=MIN_AMOUNT_GBP,
        max_value=MAX_AMOUNT_GBP,
        help_text=f"Between £{MIN_AMOUNT_GBP} and £{MAX_AMOUNT_GBP:,}, in whole pounds.",
    )
    term_months = forms.TypedChoiceField(
        label="Repayment period", coerce=int,
        choices=[(t, f"{t} month{'s' if t > 1 else ''}") for t in TERM_CHOICES],
    )
    purpose = forms.ChoiceField(label="What is the loan for?", choices=LoanApplication.Purpose.choices)

    # Personal
    title = forms.ChoiceField(choices=TITLE_CHOICES, required=False)
    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60)
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), validators=[v.validate_adult])
    email = forms.EmailField()
    phone = forms.CharField(label="Mobile or telephone", max_length=16, validators=[v.validate_uk_phone])
    ni_number = forms.CharField(label="National Insurance number", max_length=13, validators=[v.validate_ni_number])

    # Address
    address_line1 = forms.CharField(label="Address line 1", max_length=100)
    address_line2 = forms.CharField(label="Address line 2", max_length=100, required=False)
    town = forms.CharField(label="Town or city", max_length=60)
    county = forms.CharField(max_length=60, required=False)
    postcode = forms.CharField(max_length=8, validators=[v.validate_uk_postcode])
    years_at_address = forms.IntegerField(label="Years at this address", min_value=0, max_value=99)
    uk_resident = forms.BooleanField(label="I live in the UK and have the right to reside here")

    # Employment and finances
    employment_status = forms.ChoiceField(choices=LoanApplication.Employment.choices)
    employer_name = forms.CharField(max_length=100, required=False)
    housing_status = forms.ChoiceField(choices=LoanApplication.Housing.choices)
    monthly_income = MoneyField(label="Monthly take-home pay (£)")
    monthly_housing = MoneyField(label="Monthly rent or mortgage (£)")
    monthly_credit = MoneyField(label="Monthly credit repayments (£)", help_text="Cards, loans, finance and buy now pay later.")
    monthly_other = MoneyField(label="Other essential monthly spending (£)", help_text="Bills, food, transport, childcare.")

    # Bank
    account_holder_name = forms.CharField(label="Name on the account", max_length=70)
    bank_name = forms.CharField(max_length=70, required=False)
    sort_code = forms.CharField(max_length=8, validators=[v.validate_sort_code], widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "12-34-56"}))
    account_number = forms.CharField(max_length=10, validators=[v.validate_account_number], widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}))

    # Consents
    accepted_terms = forms.BooleanField(label="I confirm the information is accurate and accept the terms of this application")
    consented_credit_check = forms.BooleanField(label="I agree to identity, fraud and credit reference checks")
    marketing_opt_in = forms.BooleanField(label="Send me product news by email (optional)", required=False)

    SECTIONS = [
        ("Your loan", ["amount", "term_months", "purpose"]),
        ("About you", ["title", "first_name", "last_name", "date_of_birth", "email", "phone", "ni_number"]),
        ("Your address", ["address_line1", "address_line2", "town", "county", "postcode", "years_at_address", "uk_resident"]),
        ("Income and outgoings", ["employment_status", "employer_name", "housing_status", "monthly_income", "monthly_housing", "monthly_credit", "monthly_other"]),
        ("Your UK bank account", ["account_holder_name", "bank_name", "sort_code", "account_number"]),
        ("Confirm", ["accepted_terms", "consented_credit_check", "marketing_opt_in"]),
    ]

    def sections(self):
        return [(title, [self[name] for name in names]) for title, names in self.SECTIONS]

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_phone(self):
        return v.normalise_phone(self.cleaned_data["phone"])

    def clean_ni_number(self):
        return v.normalise_ni_number(self.cleaned_data["ni_number"])

    def clean_postcode(self):
        return v.normalise_postcode(self.cleaned_data["postcode"])

    def clean_sort_code(self):
        return v.format_sort_code(self.cleaned_data["sort_code"])

    def clean_account_number(self):
        return v.normalise_account_number(self.cleaned_data["account_number"])

    def clean(self):
        data = super().clean()
        if data.get("employment_status") in {"full_time", "part_time"} and not data.get("employer_name", "").strip():
            self.add_error("employer_name", "Tell us who you work for.")
        income = data.get("monthly_income")
        if income is not None and income <= 0:
            self.add_error("monthly_income", "Enter your monthly take-home pay.")
        return data
