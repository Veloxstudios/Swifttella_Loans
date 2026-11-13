from django.contrib import admin
from django.urls import include, path

from loans.security import guarded_login

admin.site.site_header = "Swiftella Loans administration"
admin.site.site_title = "Swiftella Loans"
admin.site.index_title = "Applications database"

urlpatterns = [
    # Staff sign-in goes through a lockout after repeated failures.
    path("staff/login/", guarded_login(admin.site.login), name="staff_login"),
    path("staff/", admin.site.urls),
    path("", include("loans.urls")),
]
