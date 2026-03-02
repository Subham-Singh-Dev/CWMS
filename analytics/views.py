from django.shortcuts import render

from datetime import date
from django.shortcuts import render
from django.utils import timezone

from .services.owner_analytics import OwnerAnalyticsService


def king_dashboard(request):
    today = timezone.now().date()
    selected_month = today.replace(day=1)

    service = OwnerAnalyticsService()
    kpis = service.get_kpis(selected_month)

    context = {
        "today": today,
        "time_of_day": _get_time_of_day(),
        **kpis,
    }

    # TEMP FIX for charts
    context.update({
        "chart_labels": [],
        "revenue_data": [],
        "expense_data": [],
        "payroll_data": [],
        "role_labels": [],
        "role_counts": [],
        "recent_activities": [],
    })

    return render(request, "portal/king_dashboard.html", context)


def _get_time_of_day():
    hour = timezone.now().hour
    if hour < 12:
        return "Morning"
    elif hour < 17:
        return "Afternoon"
    return "Evening"
