from django.conf import settings


def branding(_request):
    return {
        "BRAND_COMPANY_NAME": settings.BRAND_COMPANY_NAME,
        "BRAND_SHORT_NAME": settings.BRAND_SHORT_NAME,
        "BRAND_PRODUCT_NAME": settings.BRAND_PRODUCT_NAME,
        "BRAND_ACCOUNT_NAME": settings.BRAND_ACCOUNT_NAME,
    }
