from django.conf import settings


def site_links(request):
    return {"main_site": settings.MAIN_SITE_URL}
