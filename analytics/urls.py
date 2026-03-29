from django.urls import path
from . import views

urlpatterns = [
    path('king/audit/', views.king_audit_history, name='king_audit_history'),
    path('king/audit/export/csv/', views.king_audit_export_csv, name='king_audit_export_csv'),
    path('king/audit/export/pdf/', views.king_audit_export_pdf, name='king_audit_export_pdf'),
    path('portal/manager/audit/', views.manager_audit_history, name='manager_audit_history'),
    path('portal/manager/audit/export/csv/', views.manager_audit_export_csv, name='manager_audit_export_csv'),
    path('portal/manager/audit/export/pdf/', views.manager_audit_export_pdf, name='manager_audit_export_pdf'),
]