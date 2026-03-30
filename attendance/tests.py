from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from attendance.models import Attendance
from employees.models import Employee, Role


class AttendanceModelTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='worker1', password='pass1234')
		self.role = Role.objects.create(name='Worker', overtime_rate_per_hour=Decimal('50.00'))
		self.employee = Employee.objects.create(
			user=self.user,
			name='Test Worker',
			role=self.role,
			daily_wage=Decimal('500.00'),
			join_date=timezone.now().date(),
		)

	def test_save_allows_current_month_date(self):
		attendance = Attendance(
			employee=self.employee,
			date=timezone.now().date(),
			status='P',
			overtime_hours=Decimal('1.0'),
		)

		attendance.save()
		self.assertEqual(Attendance.objects.count(), 1)

	def test_save_rejects_future_date(self):
		tomorrow = timezone.now().date() + timezone.timedelta(days=1)
		attendance = Attendance(
			employee=self.employee,
			date=tomorrow,
			status='P',
			overtime_hours=Decimal('0.0'),
		)

		with self.assertRaises(ValidationError):
			attendance.save()

	def test_save_rejects_previous_month(self):
		today = timezone.now().date()
		if today.month == 1:
			previous_month_date = date(today.year - 1, 12, 15)
		else:
			previous_month_date = date(today.year, today.month - 1, 15)

		attendance = Attendance(
			employee=self.employee,
			date=previous_month_date,
			status='P',
			overtime_hours=Decimal('0.0'),
		)

		with self.assertRaises(ValidationError):
			attendance.save()

	def test_save_rejects_overtime_for_absent(self):
		attendance = Attendance(
			employee=self.employee,
			date=timezone.now().date(),
			status='A',
			overtime_hours=Decimal('1.0'),
		)

		with self.assertRaises(ValidationError):
			attendance.save()
