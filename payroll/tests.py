from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance
from employees.models import Employee, Role
from payroll.models import MonthlySalary, Advance
from payroll.services import generate_monthly_salary


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

	def test_generate_monthly_salary_applies_pf_esic_and_total_deductions(self):
		today = timezone.now().date()
		month_start = today.replace(day=1)

		self.employee.pf_applicable = True
		self.employee.esic_applicable = True
		self.employee.pf_rate = Decimal('0.1200')
		self.employee.esic_rate = Decimal('0.0075')
		self.employee.save(update_fields=['pf_applicable', 'esic_applicable', 'pf_rate', 'esic_rate'])

		Attendance.objects.create(
			employee=self.employee,
			date=today,
			status='P',
			overtime_hours=Decimal('1.0'),
		)

		Advance.objects.create(
			employee=self.employee,
			amount=Decimal('100.00'),
			remaining_amount=Decimal('100.00'),
			issued_date=today,
		)

		salary = generate_monthly_salary(self.employee, month_start)

		self.assertEqual(salary.gross_pay, Decimal('600.00'))
		self.assertEqual(salary.advance_deducted, Decimal('100.00'))
		self.assertEqual(salary.pf_deduction, Decimal('72.00'))
		self.assertEqual(salary.esic_deduction, Decimal('4.50'))
		self.assertEqual(salary.total_deductions, Decimal('176.50'))
		self.assertEqual(salary.net_pay, Decimal('423.50'))
		self.assertEqual(salary.pf_rate_snapshot, Decimal('0.1200'))
		self.assertEqual(salary.esic_rate_snapshot, Decimal('0.0075'))


class MonthlySalaryIntegrityTests(TestCase):
	def setUp(self):
		self.role = Role.objects.create(name='Integrity Worker', overtime_rate_per_hour=Decimal('100.00'))
		self.user = User.objects.create_user(username='integrity-emp', password='pass1234')
		self.employee = Employee.objects.create(
			user=self.user,
			name='Integrity Employee',
			role=self.role,
			daily_wage=Decimal('500.00'),
			join_date=timezone.now().date().replace(day=1),
			is_active=True,
		)

	def test_clean_passes_for_consistent_record(self):
		salary = MonthlySalary(
			employee=self.employee,
			month=timezone.now().date().replace(day=1),
			days_present=20,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('10000.00'),
			advance_deducted=Decimal('500.00'),
			pf_deduction=Decimal('1200.00'),
			esic_deduction=Decimal('75.00'),
			total_deductions=Decimal('1775.00'),
			net_pay=Decimal('8225.00'),
		)

		salary.clean()

	def test_clean_fails_for_wrong_total_deductions(self):
		salary = MonthlySalary(
			employee=self.employee,
			month=timezone.now().date().replace(day=1),
			days_present=20,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('10000.00'),
			advance_deducted=Decimal('500.00'),
			pf_deduction=Decimal('1200.00'),
			esic_deduction=Decimal('75.00'),
			total_deductions=Decimal('1800.00'),
			net_pay=Decimal('8200.00'),
		)

		with self.assertRaises(ValidationError) as ctx:
			salary.clean()

		self.assertIn('total_deductions', ctx.exception.message_dict)

	def test_clean_fails_for_wrong_net_pay(self):
		salary = MonthlySalary(
			employee=self.employee,
			month=timezone.now().date().replace(day=1),
			days_present=20,
			half_days=0,
			paid_leaves=0,
			overtime_hours=Decimal('0.00'),
			gross_pay=Decimal('10000.00'),
			advance_deducted=Decimal('500.00'),
			pf_deduction=Decimal('1200.00'),
			esic_deduction=Decimal('75.00'),
			total_deductions=Decimal('1775.00'),
			net_pay=Decimal('8200.00'),
		)

		with self.assertRaises(ValidationError) as ctx:
			salary.clean()

		self.assertIn('net_pay', ctx.exception.message_dict)
