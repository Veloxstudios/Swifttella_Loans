from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from . import validators as v
from .models import AuditEvent, Customer, LoanApplication
from .pricing import quote


def valid_post(**overrides):
    data = {
        "amount": "500", "purpose": "car_repair",
        "title": "Ms", "first_name": "Jane", "last_name": "Doe", "date_of_birth": "1990-05-17",
        "email": "Jane.Doe@Example.com", "phone": "07700 900123", "ni_number": "jg 10 37 33 c",
        "address_line1": "10 Downing Street", "town": "London", "postcode": "sw1a2aa",
        "years_at_address": "3", "uk_resident": "on",
        "employment_status": "full_time", "employer_name": "Acme Ltd", "housing_status": "renting",
        "monthly_income": "2200.50", "monthly_housing": "800", "monthly_credit": "50", "monthly_other": "600",
        "account_holder_name": "Jane Doe", "bank_name": "Example Bank", "sort_code": "12-34-56",
        "account_number": "12345678", "accepted_terms": "on", "consented_credit_check": "on",
    }
    data.update(overrides)
    return data


class PricingTests(TestCase):
    def test_one_month_matches_live_calculator(self):
        q = quote(10000, 1, start=date(2026, 1, 31))  # £100 for 30 days
        self.assertEqual(q.total_charges_pence, 2400)  # 0.8% x 30 days
        self.assertEqual(q.processing_fee_pence, 1500)
        self.assertEqual(q.interest_pence, 900)
        self.assertEqual(q.total_repayable_pence, 12400)
        self.assertEqual(q.instalments[0].due_date, date(2026, 3, 2))  # 30 days later

    def test_live_calculator_example_500(self):
        q = quote(50000, 1)
        self.assertEqual(q.interest_pence, 10500)
        self.assertEqual(q.processing_fee_pence, 1500)
        self.assertEqual(q.total_charges_pence, 12000)
        self.assertEqual(q.total_repayable_pence, 62000)
        self.assertEqual(str(q.apr_percent), "1269.7")

    def test_rates_page_example_1000(self):
        q = quote(100000, 1)  # "£225 interest and the proposed £15 fee; the repayment is £1,240"
        self.assertEqual(q.interest_pence, 22500)
        self.assertEqual(q.total_charges_pence, 24000)
        self.assertEqual(q.total_repayable_pence, 124000)

    def test_single_repayment_equals_total(self):
        for amount in (10000, 33333, 77777, 100000):
            q = quote(amount, 1)
            self.assertEqual(len(q.instalments), 1)
            self.assertEqual(q.instalments[0].amount_pence, q.total_repayable_pence)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            quote(9999, 1)
        with self.assertRaises(ValueError):
            quote(10000, 3)


class ValidatorTests(TestCase):
    def test_postcodes(self):
        for good in ["SW1A 1AA", "sw1a1aa", "M1 1AE", "B33 8TH", "CR2 6XH", "DN55 1PT", "EC1A 1BB"]:
            v.validate_uk_postcode(good)
        for bad in ["12345", "ZZZ 999", "SW1A", "Q1 1AA"]:
            with self.assertRaises(v.ValidationError):
                v.validate_uk_postcode(bad)

    def test_ni_numbers(self):
        v.validate_ni_number("JG 10 37 33 C")
        with self.assertRaises(v.ValidationError):
            v.validate_ni_number("QQ 12 34 56 C")
        v.validate_ni_number("ab123456d")
        for bad in ["GB123456A", "DA123456A", "AB123456E", "AB12345A", "ZZ123456A"]:
            with self.assertRaises(v.ValidationError):
                v.validate_ni_number(bad)

    def test_bank_details(self):
        v.validate_sort_code("12-34-56")
        v.validate_sort_code("123456")
        v.validate_account_number("12345678")
        for bad in ["1234567", "123456789", "1234567a"]:
            with self.assertRaises(v.ValidationError):
                v.validate_account_number(bad)
        with self.assertRaises(v.ValidationError):
            v.validate_sort_code("12-34-5")

    def test_adult(self):
        v.validate_adult(date(2008, 1, 1), today=date(2026, 1, 1))
        with self.assertRaises(v.ValidationError):
            v.validate_adult(date(2008, 1, 2), today=date(2026, 1, 1))


class ApplicationFlowTests(TestCase):
    def submit(self, **overrides):
        return self.client.post(reverse("loans:apply"), valid_post(**overrides))

    def test_form_renders(self):
        r = self.client.get(reverse("loans:apply"))
        self.assertContains(r, "Apply for a loan")
        self.assertContains(r, "csrfmiddlewaretoken")

    def test_submission_saves_to_database_and_returns_pdf(self):
        r = self.submit()
        app = LoanApplication.objects.get()
        self.assertRedirects(r, reverse("loans:submitted", args=[app.public_id]))
        c = app.customer
        self.assertEqual(c.email, "jane.doe@example.com")
        self.assertEqual(c.postcode, "SW1A 2AA")
        self.assertEqual(c.ni_number, "JG103733C")
        self.assertEqual(app.sort_code, "12-34-56")
        self.assertEqual(app.account_last4, "5678")
        self.assertEqual(app.monthly_income_pence, 220050)
        self.assertEqual(app.amount_pence, 50000)
        self.assertEqual(app.total_repayable_pence, 62000)  # £500 + 0.8% x 30 days
        self.assertEqual(app.term_months, 1)
        self.assertEqual(app.repayments.count(), 1)
        self.assertTrue(app.reference.startswith("SWL-"))
        self.assertTrue(app.invoice_number.startswith("INV-"))

        page = self.client.get(r.url)
        self.assertContains(page, app.reference)
        pdf = self.client.get(reverse("loans:invoice", args=[app.public_id]) + "?download=1")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn("attachment", pdf["Content-Disposition"])
        self.assertTrue(AuditEvent.objects.filter(application=app, action="invoice_downloaded").exists())

    def test_sensitive_fields_are_encrypted_at_rest(self):
        self.submit()
        with connection.cursor() as cur:
            cur.execute("SELECT account_number FROM loans_loanapplication")
            raw_acct = cur.fetchone()[0]
            cur.execute("SELECT ni_number FROM loans_customer")
            raw_ni = cur.fetchone()[0]
        self.assertNotIn("12345678", raw_acct)
        self.assertNotIn("JG103733C", raw_ni)

    def test_invoice_not_available_to_other_visitors(self):
        self.submit()
        app = LoanApplication.objects.get()
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(reverse("loans:invoice", args=[app.public_id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("loans:submitted", args=[app.public_id])).status_code, 404)

    def test_staff_can_open_any_invoice(self):
        self.submit()
        app = LoanApplication.objects.get()
        self.client.cookies.clear()
        staff = get_user_model().objects.create_user("staff", password="a-long-test-password", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("loans:invoice", args=[app.public_id])).status_code, 200)

    def test_invalid_submission_shows_errors_and_saves_nothing(self):
        r = self.submit(sort_code="12", ni_number="bad", postcode="nope", amount="5000", accepted_terms="")
        self.assertEqual(r.status_code, 200)
        for field in ("sort_code", "ni_number", "postcode", "amount", "accepted_terms"):
            self.assertIn(field, r.context["form"].errors)
        self.assertEqual(LoanApplication.objects.count(), 0)

    def test_employed_applicant_needs_employer(self):
        r = self.submit(employer_name="")
        self.assertIn("employer_name", r.context["form"].errors)

    def test_returning_customer_reuses_record(self):
        self.submit()
        self.client.cookies.clear()
        self.submit(postcode="M1 1AE", amount="200")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(LoanApplication.objects.count(), 2)
        self.assertEqual(Customer.objects.get().postcode, "M1 1AE")

    def test_email_cannot_overwrite_another_persons_record(self):
        self.submit()
        self.client.cookies.clear()
        r = self.submit(ni_number="AB123456D", address_line1="Somewhere else")
        self.assertIn("email", r.context["form"].errors)
        self.assertEqual(Customer.objects.get().address_line1, "10 Downing Street")
        self.assertEqual(LoanApplication.objects.count(), 1)


class AdminTests(TestCase):
    def test_admin_lists_and_masks(self):
        self.client.post(reverse("loans:apply"), valid_post())
        app = LoanApplication.objects.get()
        admin = get_user_model().objects.create_superuser("boss", "boss@example.com", "a-long-test-password")
        self.client.force_login(admin)
        r = self.client.get(reverse("admin:loans_loanapplication_change", args=[app.pk]))
        self.assertContains(r, "****5678")
        self.assertNotContains(r, "12345678")
        r = self.client.get(reverse("admin:loans_loanapplication_changelist"))
        self.assertContains(r, app.reference)
        r = self.client.post(reverse("admin:loans_loanapplication_changelist"),
                             {"action": "export_csv", "_selected_action": [app.pk]})
        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertNotIn(b"12345678", r.content)


class AmountStepTests(TestCase):
    def test_amount_must_be_a_50_pound_step(self):
        r = self.client.post(reverse("loans:apply"), valid_post(amount="525"))
        self.assertIn("amount", r.context["form"].errors)
        r = self.client.post(reverse("loans:apply"), valid_post(amount="550"))
        self.assertEqual(r.status_code, 302)
