from django.urls import path
from .views import (
    RecentActivityAPIView,
    AttendanceListAPIView,
    EmployeeListAPIView,
    PayrollListAPIView,
    AdvanceListAPIView,
)

urlpatterns = [
    path('activity/', RecentActivityAPIView.as_view(), name='api-activity'),
    path('attendance/', AttendanceListAPIView.as_view(), name='api-attendance'),
    path('employees/', EmployeeListAPIView.as_view(), name='api-employees'),
    path('payroll/', PayrollListAPIView.as_view(), name='api-payroll'),
    path('advances/', AdvanceListAPIView.as_view(), name='api-advances'),
]