from django.urls import path
from . import views

app_name = "expenses"

urlpatterns = [
    path("manager/expenses/", views.expense_dashboard, name="expense_dashboard"),

    path(
    "manager/expenses/delete/<int:expense_id>/",
    views.delete_expense,
    name="delete_expense",
    ),

    path(
    "manager/expenses/edit/<int:expense_id>/",
    views.edit_expense,
    name="edit_expense",
    ),

    path(
    "manager/expenses/export/",
    views.export_expenses_csv,
    name="export_expenses_csv",
    ),

    path(
    "manager/expenses/pdf/",
    views.daily_expense_pdf,
    name="daily_expense_pdf",
    ),


]