from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max, IntegerField
from django.db.models.functions import Cast, Substr
from .models import Employee
import secrets


def create_employee_with_user(
    name,
    phone_number,
    role,
    daily_wage,
    join_date,
    is_active=True
):
    with transaction.atomic():

        # Generate next EMP ID
        last_num = (
            User.objects
            .filter(username__startswith="EMP")
            .annotate(
                num=Cast(Substr('username', 4), IntegerField())
            )
            .aggregate(max_num=Max('num'))
            .get('max_num')
        ) or 0

        new_id = last_num + 1
        username = f"EMP{new_id:05d}"

        temp_password = secrets.token_urlsafe(8)

        # Create User
        user = User.objects.create_user(
            username=username,
            password=temp_password,
            is_active=is_active
        )

        # Create Employee (WITH validation)
        employee = Employee(
            user=user,
            name=name,
            phone_number=phone_number,
            role=role,
            daily_wage=daily_wage,
            join_date=join_date,
            is_active=is_active
        )

        employee.full_clean()   # 🔥 This enforces model clean()
        employee.save()

        return employee, temp_password