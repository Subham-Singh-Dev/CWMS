"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # SECURITY: Django admin endpoint; restrict with strong credentials and network controls in production.
    path('admin/', admin.site.urls),
    
    # Payroll module routes are namespaced by 'payroll/' for explicit financial workflow separation.
    path('payroll/', include('payroll.urls')),

    # Portal handles login + manager/worker dashboards.
    path('portal/', include('portal.urls')),

    # Billing endpoints mounted at root for legacy URL compatibility.
    path("", include("billing.urls")),

    # Expense endpoints mounted at root for manager navigation continuity.
    path("", include("expenses.urls")),

    # Employee master routes mounted at root for HR operations.
    path("", include("employees.urls")),

    # Analytics routes include manager and king audit history/export endpoints.
    path("", include("analytics.urls")),

    
    # King module is namespaced and isolated under /king/ for strict owner workflow boundaries.
    path('king/', include('king.urls', namespace='king')),

    
]

urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT
)
