from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Swiftella Loans administration"
admin.site.site_title = "Swiftella Loans"
admin.site.index_title = "Applications database"

urlpatterns = [
    path("staff/", admin.site.urls),
    path("", include("loans.urls")),
]
