from django.urls import path
from .views import (
    RecentActivityAPIView,
    AttendanceListAPIView,
    EmployeeListAPIView,
)

urlpatterns = [
    path('activity/', RecentActivityAPIView.as_view(), name='api-activity'),
    path('attendance/', AttendanceListAPIView.as_view(), name='api-attendance'),
    path('employees/', EmployeeListAPIView.as_view(), name='api-employees'),
]