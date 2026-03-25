from django.shortcuts import render
from portal.decorators import manager_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from .models import Role, Employee
from .services import create_employee_with_user


@login_required
@manager_required
def add_employee_view(request):

    roles = Role.objects.filter(is_active=True)

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone_number")
        role_id = request.POST.get("role")
        daily_wage = request.POST.get("daily_wage")
        join_date = request.POST.get("join_date")
        is_active = request.POST.get("is_active") == "True"
        father_name       = request.POST.get("father_name")
        email             = request.POST.get("email") or None,
        current_address   = request.POST.get("current_address"),
        permanent_address = request.POST.get("permanent_address"),
        working_location  = request.POST.get("working_location"),
        aadhar_number     = request.POST.get("aadhar_number") or None,
        pan_number        = request.POST.get("pan_number") or None,
        uan_number        = request.POST.get("uan_number") or None,
        esic_number       = request.POST.get("esic_number") or None,
        bank_account_no   = request.POST.get("bank_account_no") or None,

        # ✅ Prevent duplicate phone BEFORE service call
        if phone and Employee.objects.filter(phone_number=phone).exists():
            return render(
                request,
                "employees/add_employee.html",
                {
                    "roles": roles,
                    "error": "Phone number already exists."
                }
            )

        role = Role.objects.get(id=role_id)

        try:
            employee, temp_password = create_employee_with_user(
                name=name,
                phone_number=phone,
                role=role,
                daily_wage=daily_wage,
                join_date=join_date,
                is_active=is_active
            )

            return render(
                request,
                "employees/add_employee.html",
                {
                    "roles": roles,
                    "success": True,
                    "system_id": employee.user.username,
                    "temp_password": temp_password
                }
            )

        except ValidationError as e:
            return render(
                request,
                "employees/add_employee.html",
                {
                    "roles": roles,
                    "error": str(e)
                }
            )

    return render(
        request,
        "employees/add_employee.html",
        {"roles": roles}
    )


@login_required
@manager_required
def edit_employee_view(request, employee_id):

    roles = Role.objects.filter(is_active=True)
    employee = Employee.objects.select_related("user").get(id=employee_id)

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone_number")
        role_id = request.POST.get("role")
        daily_wage = request.POST.get("daily_wage")
        join_date = request.POST.get("join_date")
        is_active = request.POST.get("is_active") == "true"

        # Duplicate phone check (exclude current employee)
        if phone and Employee.objects.filter(phone_number=phone).exclude(id=employee.id).exists():
            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "error": "Phone number already exists."
            })

        role = Role.objects.get(id=role_id)

        try:
            employee.name = name
            employee.phone_number = phone
            employee.role = role
            employee.daily_wage = daily_wage
            employee.join_date = join_date
            employee.is_active = is_active

            employee.full_clean()
            employee.save()

            # Sync user active status
            if employee.user.is_active != is_active:
                employee.user.is_active = is_active
                employee.user.save(update_fields=["is_active"])

            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "success": "Employee updated successfully."
            })

        except ValidationError as e:
            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "error": str(e)
            })

    return render(request, "employees/edit_employee.html", {
        "roles": roles,
        "employee": employee
    })

@login_required
@manager_required
def employee_list_view(request):
    employees = Employee.objects.select_related("role", "user").all()
    roles = Role.objects.filter(is_active=True)

    search = request.GET.get("search")
    role_id = request.GET.get("role")
    status = request.GET.get("status")

    if search:
        employees = employees.filter(name__icontains=search)

    if role_id:
        employees = employees.filter(role_id=role_id)

    if status == "active":
        employees = employees.filter(is_active=True)
    elif status == "inactive":
        employees = employees.filter(is_active=False)

    return render(request, "employees/employee_list.html", {
        "employees": employees,
        "roles": roles
    })