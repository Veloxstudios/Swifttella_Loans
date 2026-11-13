from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import LoanApplicationForm
from .invoice import build_invoice_pdf
from .models import LoanApplication, record
from .pricing import DAILY_RATE, DAYS_PER_MONTH, PROCESSING_FEE_PENCE, TERM_CHOICES, TOTAL_COST_CAP
from .security import client_ip, limit_submissions
from .services import IdentityMismatch, create_application


def _owned(request, public_id) -> LoanApplication:
    """Return the application if this browser session submitted it, or the user is staff."""
    application = get_object_or_404(LoanApplication.objects.select_related("customer"), public_id=public_id)
    allowed = str(public_id) in request.session.get(settings.INVOICE_SESSION_KEY, [])
    if not (allowed or (request.user.is_authenticated and request.user.is_staff)):
        raise Http404
    return application


@require_http_methods(["GET", "POST"])
@limit_submissions
def apply(request):
    form = LoanApplicationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            application = create_application(form.cleaned_data, ip=client_ip(request))
        except IdentityMismatch:
            form.add_error("email", "This email address is already linked to different personal details. Please contact us.")
        else:
            owned = request.session.get(settings.INVOICE_SESSION_KEY, [])
            request.session[settings.INVOICE_SESSION_KEY] = (owned + [str(application.public_id)])[-20:]
            return redirect("loans:submitted", public_id=application.public_id)
    pricing = {
        "dailyRate": float(DAILY_RATE), "cap": float(TOTAL_COST_CAP),
        "fee": PROCESSING_FEE_PENCE / 100, "termDays": DAYS_PER_MONTH * TERM_CHOICES[0],
    }
    return render(request, "loans/apply.html", {"form": form, "pricing": pricing})


@require_GET
def submitted(request, public_id):
    application = _owned(request, public_id)
    return render(request, "loans/submitted.html", {"application": application})


@require_GET
def invoice_pdf(request, public_id):
    application = _owned(request, public_id)
    pdf = build_invoice_pdf(application)
    actor = request.user.get_username() if request.user.is_authenticated else application.customer.email
    record(application, "invoice_downloaded", application.invoice_number, actor=actor, ip=client_ip(request))
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{application.invoice_number}.pdf"'
    response["Cache-Control"] = "no-store"
    return response
