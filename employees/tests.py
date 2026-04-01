from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from employees.admin import EmployeeAdminForm
from employees.models import Employee, Role


class EmployeeModelTests(TestCase):
	def setUp(self):
		self.role = Role.objects.create(name='Worker', overtime_rate_per_hour=Decimal('50.00'))

	def test_local_employee_cannot_have_pf_or_esic_flags(self):
		user = User.objects.create_user(username='emp-local-1', password='pass1234')
		employee = Employee(
			user=user,
			name='Local Worker',
			role=self.role,
			daily_wage=Decimal('500.00'),
			join_date=date.today(),
			employment_type='LOCAL',
			pf_applicable=True,
			esic_applicable=False,
		)

		with self.assertRaises(ValidationError):
			employee.full_clean()

	def test_permanent_employee_can_have_pf_and_esic_flags(self):
		user = User.objects.create_user(username='emp-perm-1', password='pass1234')
		employee = Employee(
			user=user,
			name='Permanent Worker',
			role=self.role,
			daily_wage=Decimal('500.00'),
			join_date=date.today(),
			employment_type='PERMANENT',
			pf_applicable=True,
			esic_applicable=True,
		)

		employee.full_clean()


class AdminFormValidationTests(TestCase):
	def setUp(self):
		self.role = Role.objects.create(name='Mason', overtime_rate_per_hour=Decimal('60.00'))

	def test_local_employee_pf_flag_blocked_in_admin_form(self):
		form = EmployeeAdminForm(data={
			'name': 'Worker PF',
			'phone_number': '9999999991',
			'role': self.role.id,
			'daily_wage': '500.00',
			'join_date': date.today().isoformat(),
			'is_active': True,
			'employment_type': 'LOCAL',
			'pf_applicable': True,
			'esic_applicable': False,
			'pf_rate': '0.1200',
			'esic_rate': '0.0075',
		})

		self.assertFalse(form.is_valid())
		self.assertTrue('pf_applicable' in form.errors or '__all__' in form.errors)

	def test_local_employee_esic_flag_blocked_in_admin_form(self):
		form = EmployeeAdminForm(data={
			'name': 'Worker ESIC',
			'phone_number': '9999999992',
			'role': self.role.id,
			'daily_wage': '500.00',
			'join_date': date.today().isoformat(),
			'is_active': True,
			'employment_type': 'LOCAL',
			'pf_applicable': False,
			'esic_applicable': True,
			'pf_rate': '0.1200',
			'esic_rate': '0.0075',
		})

		self.assertFalse(form.is_valid())
		self.assertTrue('esic_applicable' in form.errors or '__all__' in form.errors)

	def test_permanent_employee_pf_esic_allowed_in_admin_form(self):
		form = EmployeeAdminForm(data={
			'name': 'Worker Permanent',
			'phone_number': '9999999993',
			'role': self.role.id,
			'daily_wage': '500.00',
			'join_date': date.today().isoformat(),
			'is_active': True,
			'employment_type': 'PERMANENT',
			'pf_applicable': True,
			'esic_applicable': True,
			'pf_rate': '0.1200',
			'esic_rate': '0.0075',
		})

		self.assertTrue(form.is_valid())
