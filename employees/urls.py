from django.urls import path
from . import views

urlpatterns = [
    path("manager/employees/add/", views.add_employee_view, name="add_employee"),

    path("manager/employees/edit/<int:employee_id>/", views.edit_employee_view, name="edit_employee"),

    path("manager/employees/", views.employee_list_view, name="employee_list"),
]