from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.apply, name="apply"),
    path("application/<uuid:public_id>/", views.submitted, name="submitted"),
    path("application/<uuid:public_id>/invoice.pdf", views.invoice_pdf, name="invoice"),
]
