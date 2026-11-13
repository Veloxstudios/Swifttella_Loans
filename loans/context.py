from django.conf import settings

def site_links(request):
    return {
        "main_site": settings.MAIN_SITE_URL,
        "retention_months": max(1, settings.DATA_RETENTION_DAYS // 30),
        "lender": {
            "name": settings.LENDER_NAME,
            "address": settings.LENDER_ADDRESS,
            "fca_number": settings.LENDER_FCA_NUMBER,
            "company_number": settings.LENDER_COMPANY_NUMBER,
            "ico_number": settings.LENDER_ICO_NUMBER,
            "email": settings.LENDER_EMAIL,
        },
        "price_comparison": {"url": settings.PRICE_COMPARISON_URL, "name": settings.PRICE_COMPARISON_NAME},
    }
