from django.urls import path
from .views import king_dashboard

urlpatterns = [
    path("king/dashboard/", king_dashboard, name="king_dashboard"),
]