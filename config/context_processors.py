from django.conf import settings
from portal.models import BrandSettings


def branding(_request):
    
    brand = BrandSettings.objects.first()
    
    if brand:
        return {
            "BRAND_COMPANY_NAME": brand.company_name,
            "BRAND_SHORT_NAME": brand.short_name,
            "BRAND_PRODUCT_NAME": brand.product_name,
            "BRAND_ACCOUNT_NAME": brand.company_name.upper(),
            "BRAND_COMPANY_ADDRESS": brand.company_address,
            "BRAND_COMPANY_GSTIN": brand.company_gstin,
            # Pass both logos dynamically
            "BRAND_PORTAL_LOGO_URL": brand.portal_logo.url if brand.portal_logo else None,
            "BRAND_KING_LOGO_URL": brand.king_logo.url if brand.king_logo else None,
        }
        
    # Safe Fallback for fresh local development
    return {
        "BRAND_COMPANY_NAME": "CWMS System",
        "BRAND_SHORT_NAME": "CWMS",
        "BRAND_PRODUCT_NAME": "Construction Workforce Management",
        "BRAND_ACCOUNT_NAME": "CWMS SYSTEM",
        "BRAND_COMPANY_ADDRESS": "",
        "BRAND_COMPANY_GSTIN": "",
        "BRAND_PORTAL_LOGO_URL": None,
        "BRAND_KING_LOGO_URL": None,
    }
