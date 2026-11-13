import os
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase as DjangoTestCase
from django.test import override_settings
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from django.urls import reverse

from . import validators as v
from .models import AuditEvent, Customer, LoanApplication
from .pricing import quote


class TestCase(DjangoTestCase):
    """Every test starts with empty rate-limit counters."""

    def setUp(self):
        cache.clear()
        super().setUp()

    def login_staff(self, user):
        """Sign in as staff and pass two-factor with a one-off backup code."""
        self.client.force_login(user)
        device, _ = StaticDevice.objects.get_or_create(user=user, name="test backup codes")
        device.token_set.create(token="testcode1")
        r = self.client.post(reverse("staff_2fa_verify"), {"code": "testcode1"})
        assert r.status_code == 302, r.status_code


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
        self.login_staff(staff)
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
        self.login_staff(admin)
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


def quiet():
    return open(os.devnull, "w")


@override_settings(APPLY_RATE_LIMIT=2)
class RateLimitTests(TestCase):
    def test_too_many_applications_from_one_address_are_refused(self):
        for _ in range(2):
            self.client.cookies.clear()
            self.client.post(reverse("loans:apply"), valid_post())
        r = self.client.post(reverse("loans:apply"), valid_post())
        self.assertEqual(r.status_code, 429)
        self.assertEqual(self.client.get(reverse("loans:apply")).status_code, 200)  # viewing still works

    @override_settings(TRUSTED_PROXIES=1)
    def test_spoofed_forwarded_for_does_not_dodge_the_limit(self):
        for fake in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
            r = self.client.post(reverse("loans:apply"), valid_post(amount="5000"),
                                 HTTP_X_FORWARDED_FOR=f"{fake}, 203.0.113.9")
        self.assertEqual(r.status_code, 429)


@override_settings(LOGIN_MAX_FAILURES=3)
class StaffLoginLockoutTests(TestCase):
    def setUp(self):
        super().setUp()
        get_user_model().objects.create_user("staff", password="a-long-test-password", is_staff=True)

    def test_locks_out_after_repeated_failures(self):
        url = reverse("staff_login")
        for _ in range(3):
            self.client.post(url, {"username": "staff", "password": "wrong"})
        r = self.client.post(url, {"username": "staff", "password": "a-long-test-password"})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_correct_password_works_before_lockout(self):
        r = self.client.post(reverse("staff_login"), {"username": "staff", "password": "a-long-test-password"})
        self.assertEqual(r.status_code, 302)


class SecurityHeaderTests(TestCase):
    def test_headers(self):
        r = self.client.get(reverse("loans:apply"))
        self.assertIn("script-src 'self'", r["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", r["Content-Security-Policy"])
        self.assertIn("camera=()", r["Permissions-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")

    def test_pages_with_personal_data_are_not_cached(self):
        self.client.post(reverse("loans:apply"), valid_post())
        app = LoanApplication.objects.get()
        r = self.client.get(reverse("loans:submitted", args=[app.public_id]))
        self.assertEqual(r["Cache-Control"], "no-store")

    def test_page_shows_fca_risk_warning_and_privacy_notice(self):
        r = self.client.get(reverse("loans:apply"))
        self.assertContains(r, "Late repayment can cause you serious money problems. For help, go to")
        self.assertContains(r, "How we use your information")


class StaffControlsTests(TestCase):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser("boss", "boss@example.com", "a-long-test-password")

    def make_app(self, **overrides):
        self.client.post(reverse("loans:apply"), valid_post(**overrides))
        self.client.cookies.clear()
        return LoanApplication.objects.latest("submitted_at")

    def set_status(self, app, status):
        """Submit the admin change page the way a browser would, with the inline tables' hidden fields."""
        url = reverse("admin:loans_loanapplication_change", args=[app.pk])
        page = self.client.get(url)
        data = {"status": status}
        for inline in page.context["inline_admin_formsets"]:
            fs = inline.formset
            for name, field in fs.management_form.fields.items():
                data[f"{fs.prefix}-{name}"] = fs.management_form.initial.get(name, field.initial)
            for form in fs.forms:
                for field in form.hidden_fields():
                    value = field.value()
                    data[field.html_name] = getattr(value, "pk", value) or ""
        return self.client.post(url, data)

    def test_unaffordable_application_cannot_be_approved(self):
        # About £2,200 in and £2,150 out leaves about £50, but the repayment is £620.
        app = self.make_app(monthly_housing="1500", monthly_credit="50", monthly_other="600")
        self.assertFalse(app.passes_affordability)
        self.login_staff(self.admin)
        r = self.set_status(app, "approved")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "fails the affordability check")
        app.refresh_from_db()
        self.assertEqual(app.status, "submitted")

    def test_affordable_application_can_be_approved(self):
        app = self.make_app(monthly_housing="500", monthly_credit="0", monthly_other="300")
        self.assertTrue(app.passes_affordability)
        self.login_staff(self.admin)
        r = self.set_status(app, "approved")
        self.assertEqual(r.status_code, 302)
        app.refresh_from_db()
        self.assertEqual(app.status, "approved")
        self.assertTrue(AuditEvent.objects.filter(application=app, action="status_changed").exists())

    def test_nobody_can_delete_applications_or_customers(self):
        app = self.make_app()
        self.login_staff(self.admin)
        r = self.client.post(reverse("admin:loans_loanapplication_delete", args=[app.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post(reverse("admin:loans_customer_delete", args=[app.customer.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(LoanApplication.objects.filter(pk=app.pk).exists())

    def test_staff_views_are_recorded(self):
        app = self.make_app()
        self.login_staff(self.admin)
        self.client.get(reverse("admin:loans_loanapplication_change", args=[app.pk]))
        self.assertTrue(AuditEvent.objects.filter(application=app, action="viewed_by_staff", actor="boss").exists())


class RetentionTests(TestCase):
    def make_old_app(self, **fields):
        self.client.post(reverse("loans:apply"), valid_post())
        app = LoanApplication.objects.get()
        LoanApplication.objects.filter(pk=app.pk).update(submitted_at=timezone.now() - timedelta(days=400), **fields)
        return app

    def test_old_unfunded_applications_are_anonymised(self):
        app = self.make_old_app()
        call_command("anonymise_old_applications", stdout=quiet())  # dry run changes nothing
        app.refresh_from_db()
        self.assertIsNone(app.personal_data_removed_at)

        call_command("anonymise_old_applications", "--apply", stdout=quiet())
        app.refresh_from_db()
        c = app.customer
        self.assertIsNotNone(app.personal_data_removed_at)
        self.assertEqual(app.account_last4, "")
        self.assertEqual(c.first_name, "[removed]")
        self.assertEqual(c.ni_number, "")
        self.assertNotIn("jane", c.email)
        self.assertTrue(AuditEvent.objects.filter(application=app, action="personal_data_removed").exists())
        self.assertFalse(AuditEvent.objects.filter(application=app).exclude(actor__in=["", "retention process"]).exists())

    def test_approved_applications_are_kept(self):
        app = self.make_old_app(status="approved")
        call_command("anonymise_old_applications", "--apply", stdout=quiet())
        app.refresh_from_db()
        self.assertIsNone(app.personal_data_removed_at)
        self.assertEqual(app.customer.first_name, "Jane")


def totp_now(device):
    return TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift).token()


class StaffTwoFactorTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser("boss", "boss@example.com", "a-long-test-password")

    def test_password_alone_does_not_reach_the_admin(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("admin:loans_loanapplication_changelist"))
        self.assertRedirects(r, reverse("staff_2fa_setup") + "?next=%2Fstaff%2Floans%2Floanapplication%2F",
                             fetch_redirect_response=False)

    def test_password_alone_cannot_open_invoices(self):
        self.client.post(reverse("loans:apply"), valid_post())
        app = LoanApplication.objects.get()
        self.client.cookies.clear()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("loans:invoice", args=[app.public_id])).status_code, 404)

    def test_setup_with_authenticator_app(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("staff_2fa_setup"))
        self.assertContains(page, "data:image/svg+xml;base64,")
        device = TOTPDevice.objects.get(user=self.user, confirmed=False)

        bad = self.client.post(reverse("staff_2fa_setup"), {"code": "000000" if totp_now(device) != 0 else "111111"})
        self.assertContains(bad, "didn&#x27;t match")
        too_soon = self.client.post(reverse("staff_2fa_setup"), {"code": f"{totp_now(device):06d}"})
        self.assertContains(too_soon, "wait a few seconds")
        device.refresh_from_db()
        device.throttle_reset()  # django-otp briefly blocks retries after a wrong code; this is the wait

        r = self.client.post(reverse("staff_2fa_setup"), {"code": f"{totp_now(device):06d}"})
        self.assertContains(r, "Two-factor sign-in is on")
        self.assertEqual(len(r.context["codes"]), 10)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_returning_staff_must_enter_a_code(self):
        TOTPDevice.objects.create(user=self.user, name="phone", confirmed=True)
        self.client.force_login(self.user)
        r = self.client.get(reverse("admin:index"))
        self.assertRedirects(r, reverse("staff_2fa_verify") + "?next=%2Fstaff%2F", fetch_redirect_response=False)
        # Someone with an app set up can't start a new setup to get around it.
        r = self.client.get(reverse("staff_2fa_setup"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(reverse("staff_2fa_verify")))

    def test_backup_codes_work_once(self):
        device = StaticDevice.objects.create(user=self.user, name="Backup codes")
        device.token_set.create(token="abcd1234")
        self.client.force_login(self.user)
        r = self.client.post(reverse("staff_2fa_verify"), {"code": "abcd1234"})
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        self.client.force_login(self.user)
        r = self.client.post(reverse("staff_2fa_verify"), {"code": "abcd1234"})
        self.assertContains(r, "didn&#x27;t work")

    @override_settings(LOGIN_MAX_FAILURES=3)
    def test_wrong_codes_lock_out(self):
        TOTPDevice.objects.create(user=self.user, name="phone", confirmed=True)
        self.client.force_login(self.user)
        for _ in range(3):
            self.client.post(reverse("staff_2fa_verify"), {"code": "000000"})
        r = self.client.post(reverse("staff_2fa_verify"), {"code": "000000"})
        self.assertEqual(r.status_code, 429)

    def test_redirect_after_code_stays_on_this_site(self):
        device = StaticDevice.objects.create(user=self.user, name="Backup codes")
        device.token_set.create(token="abcd1234")
        self.client.force_login(self.user)
        r = self.client.post(reverse("staff_2fa_verify"), {"code": "abcd1234", "next": "https://evil.example/"})
        self.assertEqual(r.url, reverse("admin:index"))

    def test_reset_command_removes_devices(self):
        TOTPDevice.objects.create(user=self.user, name="phone", confirmed=True)
        StaticDevice.objects.create(user=self.user, name="Backup codes")
        call_command("reset_staff_2fa", "boss", stdout=quiet())
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())


class StaffTwoFactorAdminTests(TestCase):
    def test_otp_secret_pages_are_not_in_the_admin(self):
        boss = get_user_model().objects.create_superuser("boss", "boss@example.com", "a-long-test-password")
        self.login_staff(boss)
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse("admin:otp_static_staticdevice_changelist")
        with self.assertRaises(NoReverseMatch):
            reverse("admin:otp_totp_totpdevice_changelist")

    def test_superuser_can_reset_a_colleagues_2fa(self):
        boss = get_user_model().objects.create_superuser("boss", "boss@example.com", "a-long-test-password")
        colleague = get_user_model().objects.create_user("sam", password="a-long-test-password", is_staff=True)
        TOTPDevice.objects.create(user=colleague, name="phone", confirmed=True)
        self.login_staff(boss)
        self.client.post(reverse("admin:auth_user_changelist"),
                         {"action": "reset_two_factor", "_selected_action": [colleague.pk]})
        self.assertFalse(TOTPDevice.objects.filter(user=colleague).exists())


class ConfirmationEmailTests(TestCase):
    def test_customer_gets_an_email_with_the_invoice(self):
        from django.core import mail
        self.client.post(reverse("loans:apply"), valid_post())
        app = LoanApplication.objects.get()
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [app.customer.email])
        self.assertIn(app.reference, msg.subject)
        self.assertIn("No lending decision has been made yet", msg.body)
        self.assertIn("Late repayment can cause you serious money problems", msg.body)
        html = msg.alternatives[0][0]
        self.assertIn(app.total_repayable_display, html)
        name, content, mimetype = msg.attachments[0]
        self.assertEqual(name, f"{app.invoice_number}.pdf")
        self.assertTrue(content.startswith(b"%PDF"))
        # Never the full NI or bank account number.
        for secret in (app.customer.ni_number, app.account_number):
            self.assertNotIn(secret, msg.body)
            self.assertNotIn(secret, html)
        self.assertTrue(AuditEvent.objects.filter(application=app, action="confirmation_email_sent").exists())

    def test_email_failure_does_not_lose_the_application(self):
        from unittest import mock
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp down")), \
                self.assertLogs("loans.emails", "ERROR"):
            r = self.client.post(reverse("loans:apply"), valid_post())
        app = LoanApplication.objects.get()
        self.assertRedirects(r, reverse("loans:submitted", args=[app.public_id]))
        self.assertTrue(AuditEvent.objects.filter(application=app, action="confirmation_email_failed").exists())
