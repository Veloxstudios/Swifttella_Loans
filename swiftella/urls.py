from django.contrib import admin
from django.urls import include, path

from loans import twofactor
from loans.security import guarded_login

admin.site.site_header = "Swiftella Loans administration"
admin.site.site_title = "Swiftella Loans"
admin.site.index_title = "Applications database"

urlpatterns = [
    # Staff sign-in goes through a lockout after repeated failures.
    path("staff/login/", guarded_login(admin.site.login), name="staff_login"),
    # Every staff member must also enter a code from an authenticator app.
    path("staff/2fa/setup/", twofactor.setup, name="staff_2fa_setup"),
    path("staff/2fa/verify/", twofactor.verify, name="staff_2fa_verify"),
    path("staff/", admin.site.urls),
    path("", include("loans.urls")),
]
