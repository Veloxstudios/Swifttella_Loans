import csv

from django.contrib import admin
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

from .models import AuditEvent, Customer, LoanApplication, ScheduledRepayment, record
from .pricing import gbp


def _csv_safe(value):
    """Stop spreadsheet apps treating customer-typed text as a formula."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class ScheduledRepaymentInline(admin.TabularInline):
    model = ScheduledRepayment
    extra = 0
    can_delete = False
    readonly_fields = ["number", "due_date", "amount"]
    fields = readonly_fields

    @admin.display(description="Amount")
    def amount(self, obj):
        return gbp(obj.amount_pence)

    def has_add_permission(self, request, obj=None):
        return False


class AuditEventInline(admin.TabularInline):
    model = AuditEvent
    extra = 0
    can_delete = False
    readonly_fields = ["created_at", "action", "detail", "actor", "ip_address"]
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "email", "postcode", "masked_ni", "created_at"]
    search_fields = ["first_name", "last_name", "email", "postcode", "ni_last3"]
    readonly_fields = ["masked_ni", "created_at", "updated_at"]
    exclude = ["ni_number"]

    @admin.display(description="NI number")
    def masked_ni(self, obj):
        return f"******{obj.ni_last3}" if obj.ni_last3 else "—"


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ["reference", "customer", "amount", "term_months", "total_repayable", "status", "submitted_at"]
    list_filter = ["status", "term_months", "purpose", "employment_status", "submitted_at"]
    search_fields = ["reference", "invoice_number", "customer__email", "customer__last_name", "customer__postcode", "account_last4"]
    date_hierarchy = "submitted_at"
    list_select_related = ["customer"]
    inlines = [ScheduledRepaymentInline, AuditEventInline]
    actions = ["export_csv"]
    readonly_fields = [
        "reference", "invoice_number", "invoice_link", "customer", "amount", "term_months", "purpose",
        "processing_fee", "interest", "total_charges", "total_repayable", "apr_percent",
        "employment_status", "employer_name", "housing_status", "income", "outgoings", "disposable",
        "account_holder_name", "bank_name", "sort_code", "masked_account",
        "accepted_terms", "consented_credit_check", "marketing_opt_in", "submitted_ip", "submitted_at", "updated_at",
    ]
    fieldsets = [
        ("Application", {"fields": ["reference", "invoice_number", "invoice_link", "status", "customer", "submitted_at", "updated_at", "submitted_ip"]}),
        ("Loan", {"fields": ["amount", "term_months", "purpose", "processing_fee", "interest", "total_charges", "total_repayable", "apr_percent"]}),
        ("Affordability", {"fields": ["employment_status", "employer_name", "housing_status", "income", "outgoings", "disposable"]}),
        ("Bank account", {"fields": ["account_holder_name", "bank_name", "sort_code", "masked_account"]}),
        ("Consents", {"fields": ["accepted_terms", "consented_credit_check", "marketing_opt_in"]}),
    ]

    def has_add_permission(self, request):
        return False  # applications come in through the customer form only

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            record(obj, "status_changed", f"{form.initial.get('status')} → {obj.status}", actor=request.user.get_username())
        super().save_model(request, obj, form, change)

    @admin.display(description="Amount")
    def amount(self, obj):
        return gbp(obj.amount_pence)

    @admin.display(description="Processing fee")
    def processing_fee(self, obj):
        return gbp(obj.processing_fee_pence)

    @admin.display(description="Interest")
    def interest(self, obj):
        return gbp(obj.interest_pence)

    @admin.display(description="Total charges")
    def total_charges(self, obj):
        return gbp(obj.total_charges_pence)

    @admin.display(description="Total repayable")
    def total_repayable(self, obj):
        return gbp(obj.total_repayable_pence)

    @admin.display(description="Monthly income")
    def income(self, obj):
        return gbp(obj.monthly_income_pence)

    @admin.display(description="Monthly outgoings")
    def outgoings(self, obj):
        return gbp(obj.monthly_outgoings_pence)

    @admin.display(description="Disposable income")
    def disposable(self, obj):
        return gbp(obj.disposable_income_pence)

    @admin.display(description="Account number")
    def masked_account(self, obj):
        return f"****{obj.account_last4}"

    @admin.display(description="Invoice")
    def invoice_link(self, obj):
        if not obj.pk:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open PDF invoice</a>', reverse("loans:invoice", args=[obj.public_id]))

    @admin.action(description="Export selected to CSV (no NI or full account numbers)")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="applications.csv"'
        w = csv.writer(response)
        w.writerow(["reference", "invoice_number", "status", "submitted_at", "name", "email", "postcode",
                    "amount_gbp", "term_months", "total_repayable_gbp", "monthly_income_gbp", "sort_code", "account_last4"])
        for a in queryset.select_related("customer"):
            w.writerow([_csv_safe(x) for x in [a.reference, a.invoice_number, a.status, a.submitted_at.isoformat(), a.customer.full_name,
                        a.customer.email, a.customer.postcode, a.amount_pence / 100, a.term_months,
                        a.total_repayable_pence / 100, a.monthly_income_pence / 100, a.sort_code, a.account_last4]])
        return response
