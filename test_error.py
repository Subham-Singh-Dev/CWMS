#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from employees.models import Employee
from payroll.models import MonthlySalary

print('🔍 Testing for dangling salary references...')

orphaned = 0
total = 0
for salary in MonthlySalary.objects.all()[:10]:
    total += 1
    try:
        emp = salary.employee
        print(f'✅ Salary {salary.id}: Employee "{emp.name}" exists')
    except Employee.DoesNotExist:
        print(f'❌ Salary {salary.id}: Employee DELETED! (Foreign key broken)')
        orphaned += 1

print(f'\n📊 Results: {total} salaries checked, {orphaned} orphaned')

if orphaned == 0:
    print('\n✅ No orphaned records found.')
    print('Error not currently present - would need to manually delete employee with active salary.')
else:
    print(f'\n⚠️ {orphaned} orphaned salary records exist - error would trigger on form render!')
