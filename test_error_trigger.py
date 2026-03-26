#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from employees.models import Employee
from payroll.models import MonthlySalary
from django.test import RequestFactory
from django.contrib.auth.models import User, Group
from portal.views import salary_list_view

print('🧪 SIMULATING ERROR TRIGGER...\n')

# Get an employee with salary records
salary = MonthlySalary.objects.first()
if not salary:
    print('❌ No salary records in DB. Cannot test.')
    exit()

employee_id = salary.employee.id
employee_name = salary.employee.name
month = salary.month.strftime('%Y-%m')

print(f'1️⃣ Found salary record:')
print(f'   Employee: {employee_name} (ID: {employee_id})')
print(f'   Month: {month}')

# Create fake admin user
admin_user, _ = User.objects.get_or_create(
    username='test_admin',
    defaults={'is_superuser': True, 'is_staff': True}
)
Group.objects.get_or_create(name='Manager')
admin_user.groups.add(Group.objects.get(name='Manager'))

print(f'\n2️⃣ Deleting employee {employee_name}...')
Employee.objects.filter(id=employee_id).delete()
print(f'   ✅ Deleted')

print(f'\n3️⃣ Simulating request to /payroll/manager/payroll/salaries/?month={month}')

try:
    # Create fake request
    factory = RequestFactory()
    request = factory.get(f'/payroll/manager/payroll/salaries/?month={month}')
    request.user = admin_user
    
    # Try to render the view
    response = salary_list_view(request)
    print(f'   ✅ View rendered successfully')
    print(f'   Status: {response.status_code}')
    
except ValueError as e:
    if 'match one of the choices' in str(e):
        print(f'   ❌ ERROR TRIGGERED!')
        print(f'   {str(e)[:100]}...')
    else:
        raise
except Exception as e:
    print(f'   ⚠️ Different error: {type(e).__name__}: {str(e)[:80]}')

# Restore employee for safety
print(f'\n4️⃣ Restoring deleted employee (for safety)...')
# Note: In real scenario would need backup, here just informing
print(f'   ⚠️ Employee permanently deleted from DB - would need backup to restore')
