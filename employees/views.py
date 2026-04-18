"""
Module: employees.views
App: employees
Purpose: Manager-side CRUD operations for employee master records.
Dependencies: employees.models/services, manager_required decorator.
Author note: Validation is duplicated at service/model boundaries intentionally for defense in depth.
"""

from django.shortcuts import render, get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from portal.decorators import manager_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
from .models import Role, Employee
from .services import create_employee_with_user
from analytics.services.audit_service import create_audit_log


def _humanize_validation_error(exc: ValidationError) -> str:
    """Convert Django ValidationError payload into clean, readable message text."""
    if hasattr(exc, 'message_dict') and exc.message_dict:
        parts = []
        for field, messages in exc.message_dict.items():
            label = field.replace('_', ' ').title()
            for message in messages:
                parts.append(f"{label}: {message}")
        return " | ".join(parts)

    if hasattr(exc, 'messages') and exc.messages:
        return " | ".join(str(message) for message in exc.messages)

    return str(exc)


def _validation_error_list(exc: ValidationError) -> list[str]:
    """Return validation errors as clean list items for UI alerts."""
    if hasattr(exc, 'message_dict') and exc.message_dict:
        items = []
        for field, messages in exc.message_dict.items():
            label = field.replace('_', ' ').title()
            for message in messages:
                items.append(f"{label}: {message}")
        return items

    if hasattr(exc, 'messages') and exc.messages:
        return [str(message) for message in exc.messages]

    return [str(exc)]


@login_required
@manager_required
def add_employee_view(request):
    """Create employee + linked auth user using service layer."""

    roles = Role.objects.filter(is_active=True)

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone_number")
        role_id = request.POST.get("role")
        daily_wage = request.POST.get("daily_wage")
        join_date = request.POST.get("join_date")
        is_active = (request.POST.get("is_active") or "").lower() == "true"
        employment_type = request.POST.get("employment_type", "LOCAL")
        pf_applicable = request.POST.get("pf_applicable") == "on"
        esic_applicable = request.POST.get("esic_applicable") == "on"
        pf_rate = request.POST.get("pf_rate") or "0.1200"
        esic_rate = request.POST.get("esic_rate") or "0.0075"
        father_name       = request.POST.get("father_name")
        email             = request.POST.get("email") or None
        current_address   = request.POST.get("current_address")
        permanent_address = request.POST.get("permanent_address")
        working_location  = request.POST.get("working_location")
        aadhar_number     = request.POST.get("aadhar_number") or None
        pan_number        = request.POST.get("pan_number") or None
        uan_number        = request.POST.get("uan_number") or None
        esic_number       = request.POST.get("esic_number") or None
        bank_account_no   = request.POST.get("bank_account_no") or None

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

        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            messages.error(request, "Selected role is invalid or no longer available. Please choose a valid role.")
            return render(
                request,
                "employees/add_employee.html",
                {
                    "roles": roles,
                    "error": "Selected role is invalid or no longer available."
                }
            )

        if employment_type == 'LOCAL':
            pf_applicable = False
            esic_applicable = False

        try:
            pf_rate = Decimal(pf_rate).quantize(Decimal('0.0001'))
            esic_rate = Decimal(esic_rate).quantize(Decimal('0.0001'))
        except InvalidOperation:
            return render(
                request,
                "employees/add_employee.html",
                {
                    "roles": roles,
                    "error": "Invalid PF/ESIC rate format."
                }
            )

        try:
            with transaction.atomic():
                employee, temp_password = create_employee_with_user(
                    name=name,
                    phone_number=phone,
                    role=role,
                    daily_wage=daily_wage,
                    join_date=join_date,
                    is_active=is_active,
                    employment_type=employment_type,
                    pf_applicable=pf_applicable,
                    esic_applicable=esic_applicable,
                    pf_rate=pf_rate,
                    esic_rate=esic_rate,
                )

                employee.father_name = father_name
                employee.email = email
                employee.current_address = current_address
                employee.permanent_address = permanent_address
                employee.working_location = working_location
                employee.aadhar_number = aadhar_number
                employee.pan_number = pan_number
                employee.uan_number = uan_number
                employee.esic_number = esic_number
                employee.bank_account_no = bank_account_no
                employee.full_clean()
                employee.save()

                create_audit_log(
                    user=request.user,
                    username=request.user.username,
                    activity='employee',
                    action='create',
                    entity_type='Employee',
                    entity_id=employee.id,
                    entity_name=employee.name,
                    details=(
                        f"Created employee {employee.name} (System ID: {employee.user.username}) "
                        f"with role {employee.role.name}"
                    ),
                    request=request,
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
            error_items = _validation_error_list(e)
            return render(
                request,
                "employees/add_employee.html",
                {
                    "roles": roles,
                    "error": _humanize_validation_error(e),
                    "error_items": error_items,
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
    """Update employee profile and synchronize linked user active state."""

    roles = Role.objects.filter(is_active=True)
    employee = Employee.objects.select_related("user").get(id=employee_id)

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone_number")
        role_id = request.POST.get("role")
        daily_wage = request.POST.get("daily_wage")
        join_date = request.POST.get("join_date")
        is_active = request.POST.get("is_active") == "true"
        employment_type = request.POST.get("employment_type", "LOCAL")
        pf_applicable = request.POST.get("pf_applicable") == "on"
        esic_applicable = request.POST.get("esic_applicable") == "on"
        pf_rate = request.POST.get("pf_rate") or "0.1200"
        esic_rate = request.POST.get("esic_rate") or "0.0075"
        father_name = request.POST.get("father_name")
        email = request.POST.get("email") or None
        current_address = request.POST.get("current_address")
        permanent_address = request.POST.get("permanent_address")
        working_location = request.POST.get("working_location")
        aadhar_number = request.POST.get("aadhar_number") or None
        pan_number = request.POST.get("pan_number") or None
        uan_number = request.POST.get("uan_number") or None
        esic_number = request.POST.get("esic_number") or None
        bank_account_no = request.POST.get("bank_account_no") or None

        # Duplicate phone check (exclude current employee)
        if phone and Employee.objects.filter(phone_number=phone).exclude(id=employee.id).exists():
            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "error": "Phone number already exists."
            })

        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            messages.error(request, "Selected role is invalid or no longer available. Please choose a valid role.")
            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "error": "Selected role is invalid or no longer available."
            })

        if employment_type == 'LOCAL':
            pf_applicable = False
            esic_applicable = False

        try:
            pf_rate = Decimal(pf_rate).quantize(Decimal('0.0001'))
            esic_rate = Decimal(esic_rate).quantize(Decimal('0.0001'))
        except InvalidOperation:
            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "error": "Invalid PF/ESIC rate format."
            })

        try:
            with transaction.atomic():
                employee.name = name
                employee.phone_number = phone
                employee.role = role
                employee.daily_wage = daily_wage
                employee.employment_type = employment_type
                employee.pf_applicable = pf_applicable
                employee.esic_applicable = esic_applicable
                employee.pf_rate = pf_rate
                employee.esic_rate = esic_rate
                employee.join_date = join_date
                employee.is_active = is_active
                employee.father_name = father_name
                employee.email = email
                employee.current_address = current_address
                employee.permanent_address = permanent_address
                employee.working_location = working_location
                employee.aadhar_number = aadhar_number
                employee.pan_number = pan_number
                employee.uan_number = uan_number
                employee.esic_number = esic_number
                employee.bank_account_no = bank_account_no

                employee.full_clean()
                employee.save()

                # Sync user active status
                if employee.user.is_active != is_active:
                    employee.user.is_active = is_active
                    employee.user.save(update_fields=["is_active"])

                create_audit_log(
                    user=request.user,
                    username=request.user.username,
                    activity='employee',
                    action='update',
                    entity_type='Employee',
                    entity_id=employee.id,
                    entity_name=employee.name,
                    details=f"Updated employee profile for {employee.name}",
                    request=request,
                )

            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "success": "Employee updated successfully."
            })

        except ValidationError as e:
            error_items = _validation_error_list(e)
            return render(request, "employees/edit_employee.html", {
                "roles": roles,
                "employee": employee,
                "error": _humanize_validation_error(e),
                "error_items": error_items,
            })

    return render(request, "employees/edit_employee.html", {
        "roles": roles,
        "employee": employee
    })


@login_required
@manager_required
def employee_profile_view(request, employee_id):
    """Render a manager-facing read-only employee profile with quick actions."""
    employee = get_object_or_404(
        Employee.objects.select_related("role", "user"),
        id=employee_id,
    )

    return render(
        request,
        "employees/employee_profile.html",
        {"employee": employee},
    )

@login_required
@manager_required
def employee_list_view(request, viewing_as_owner=False):
    """List/filter employee master records for manager operations."""
    employees = Employee.objects.select_related("role", "user").all()
    roles = Role.objects.filter(is_active=True)

    search = request.GET.get("search")
    role_id = request.GET.get("role")
    status = request.GET.get("status")
    employment_type = request.GET.get("employment_type")

    if search:
        employees = employees.filter(
            Q(name__icontains=search) |
            Q(user__username__icontains=search)
        )

    if role_id:
        employees = employees.filter(role_id=role_id)

    if status == "active":
        employees = employees.filter(is_active=True)
    elif status == "inactive":
        employees = employees.filter(is_active=False)

    if employment_type in {"LOCAL", "PERMANENT"}:
        employees = employees.filter(employment_type=employment_type)

    total_count = employees.count()
    active_count = employees.filter(is_active=True).count()
    inactive_count = employees.filter(is_active=False).count()

    return render(request, "employees/employee_list.html", {
        "employees": employees,
        "roles": roles,
        "total_count": total_count,
        "active_count": active_count,
        "inactive_count": inactive_count,
    })