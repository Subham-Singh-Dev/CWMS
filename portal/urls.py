from django.urls import path
from . import views
from payroll import views as payroll_views

urlpatterns = [
    path('login/', views.portal_login, name='portal_login'),
    path('dashboard/', views.worker_dashboard, name='worker_dashboard'),
    path('logout/', views.worker_logout, name='worker_logout'),
    path('download-payslip/<int:salary_id>/', views.download_payslip, name='download_payslip'),

    # --- Worker Features ---
    path('profile/', views.worker_profile, name='worker_profile'),
    path('attendance/', views.worker_attendance, name='worker_attendance'),

    # --- NEW: Manager Dashboard Path ---
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/dashboard/recent-activity/', views.manager_recent_activity_api, name='manager_recent_activity_api'),

    # ✅ THIS WAS MISSING. ADD IT NOW:
    path('manager/attendance/bulk/', views.bulk_attendance, name='bulk_attendance'),

    path('manager/run-payroll/', views.run_payroll, name='run_payroll'),

    path("manager/advances/issue/", payroll_views.issue_advance_view, name="issue_advance"),


]