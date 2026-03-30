from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance
from employees.models import Employee, Role
from payroll.models import MonthlySalary


class PayrollFlowTests(TestCase):
	def setUp(self):
		self.manager_group, _ = Group.objects.get_or_create(name='Manager')
		self.user = User.objects.create_user(username='manager1', password='pass1234')
		self.user.groups.add(self.manager_group)
		self.client.login(username='manager1', password='pass1234')

		self.role = Role.objects.create(name='Payroll Worker', overtime_rate_per_hour=Decimal('100.00'))
		self.employee_user = User.objects.create_user(username='emp1', password='pass1234')
		self.employee = Employee.objects.create(
			user=self.employee_user,
			name='Employee One',
			role=self.role,
			daily_wage=Decimal('500.00'),
			join_date=timezone.now().date().replace(day=1),
			is_active=True,
		)

	def test_generate_employee_salary_creates_record_for_current_month(self):
		today = timezone.now().date()
		month_start = today.replace(day=1)
		month_str = month_start.strftime('%Y-%m')

		Attendance.objects.create(
			employee=self.employee,
			date=today,
			status='P',
			overtime_hours=Decimal('1.0'),
		)

		response = self.client.post(
			reverse('generate_employee_salary'),
			data={'employee_id': self.employee.id, 'month': month_str},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(MonthlySalary.objects.filter(employee=self.employee, month=month_start).count(), 1)

	def test_generate_employee_salary_duplicate_keeps_single_record(self):
		today = timezone.now().date()
		month_start = today.replace(day=1)
		month_str = month_start.strftime('%Y-%m')

		MonthlySalary.objects.create(
			employee=self.employee,
			month=month_start,
			days_present=1,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('500.00'),
			advance_deducted=Decimal('0.00'),
			net_pay=Decimal('500.00'),
			remaining_advance=Decimal('0.00'),
		)

		response = self.client.post(
			reverse('generate_employee_salary'),
			data={'employee_id': self.employee.id, 'month': month_str},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(MonthlySalary.objects.filter(employee=self.employee, month=month_start).count(), 1)

	def test_generate_employee_salary_denies_non_manager_user(self):
		today = timezone.now().date()
		month_start = today.replace(day=1)
		month_str = month_start.strftime('%Y-%m')

		Attendance.objects.create(
			employee=self.employee,
			date=today,
			status='P',
			overtime_hours=Decimal('0.0'),
		)

		self.client.logout()
		worker = User.objects.create_user(username='worker-payroll', password='pass1234')
		self.client.login(username='worker-payroll', password='pass1234')

		response = self.client.post(
			reverse('generate_employee_salary'),
			data={'employee_id': self.employee.id, 'month': month_str},
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(MonthlySalary.objects.filter(employee=self.employee, month=month_start).count(), 0)

	def test_mark_salary_paid_denies_non_manager_user(self):
		month_start = timezone.now().date().replace(day=1)
		salary = MonthlySalary.objects.create(
			employee=self.employee,
			month=month_start,
			days_present=1,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('500.00'),
			advance_deducted=Decimal('0.00'),
			net_pay=Decimal('500.00'),
			remaining_advance=Decimal('0.00'),
			is_paid=False,
		)

		self.client.logout()
		worker = User.objects.create_user(username='worker-mark-paid', password='pass1234')
		self.client.login(username='worker-mark-paid', password='pass1234')

		response = self.client.post(
			reverse('mark_salary_paid'),
			data={'salary_id': salary.id, 'month': month_start.strftime('%Y-%m')},
		)

		self.assertEqual(response.status_code, 403)
		salary.refresh_from_db()
		self.assertFalse(salary.is_paid)

	def test_mark_salary_paid_requires_login(self):
		month_start = timezone.now().date().replace(day=1)
		salary = MonthlySalary.objects.create(
			employee=self.employee,
			month=month_start,
			days_present=1,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('500.00'),
			advance_deducted=Decimal('0.00'),
			net_pay=Decimal('500.00'),
			remaining_advance=Decimal('0.00'),
			is_paid=False,
		)

		self.client.logout()
		response = self.client.post(
			reverse('mark_salary_paid'),
			data={'salary_id': salary.id, 'month': month_start.strftime('%Y-%m')},
		)

		self.assertEqual(response.status_code, 302)
		salary.refresh_from_db()
		self.assertFalse(salary.is_paid)

	def test_generate_employee_salary_get_returns_method_not_allowed(self):
		today = timezone.now().date()
		month_start = today.replace(day=1)
		month_str = month_start.strftime('%Y-%m')

		response = self.client.get(
			reverse('generate_employee_salary'),
			data={'employee_id': self.employee.id, 'month': month_str},
		)

		self.assertEqual(response.status_code, 405)

	def test_mark_salary_paid_get_returns_method_not_allowed(self):
		month_start = timezone.now().date().replace(day=1)
		salary = MonthlySalary.objects.create(
			employee=self.employee,
			month=month_start,
			days_present=1,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('500.00'),
			advance_deducted=Decimal('0.00'),
			net_pay=Decimal('500.00'),
			remaining_advance=Decimal('0.00'),
			is_paid=False,
		)

		response = self.client.get(
			reverse('mark_salary_paid'),
			data={'salary_id': salary.id, 'month': month_start.strftime('%Y-%m')},
		)

		self.assertEqual(response.status_code, 405)
		salary.refresh_from_db()
		self.assertFalse(salary.is_paid)
