from django.urls import path
from . import views

urlpatterns = [
    path('payslip/<int:salary_id>/', views.download_payslip, name='download_payslip'),
    path("summary/", views.payroll_batch_summary, name="payroll_batch_summary"),
    path(
    "manager/payroll/salaries/",
    views.salary_list_view,
    name="manager_salary_list"
    ),
    path(
    "manager/payroll/salaries/generate/",
    views.generate_employee_salary,
    name="generate_employee_salary"
  ),

  path(
    "manager/payroll/salaries/mark-paid/",
    views.mark_salary_paid,
    name="mark_salary_paid"
  ),

  path(
    "manager/payroll/salaries/export/",
    views.export_salary_list_csv,
    name="export_salary_list_csv"
  ),

  




    
]