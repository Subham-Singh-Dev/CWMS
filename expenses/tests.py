from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from expenses.models import Expense


class ExpensePermissionTests(TestCase):
	def setUp(self):
		self.manager_group, _ = Group.objects.get_or_create(name='Manager')
		self.manager = User.objects.create_user(username='manager-exp', password='pass1234')
		self.manager.groups.add(self.manager_group)

		self.worker = User.objects.create_user(username='worker-exp', password='pass1234')

		self.expense = Expense.objects.create(
			date=timezone.now().date(),
			category='fuel',
			description='Diesel refill',
			amount=Decimal('300.00'),
			payment_mode='cash',
			created_by=self.manager,
		)

	def test_delete_expense_denies_non_manager_user(self):
		self.client.login(username='worker-exp', password='pass1234')

		response = self.client.post(reverse('expenses:delete_expense', args=[self.expense.id]))

		self.assertEqual(response.status_code, 403)
		self.assertTrue(Expense.objects.filter(id=self.expense.id).exists())

	def test_delete_expense_requires_login(self):
		response = self.client.post(reverse('expenses:delete_expense', args=[self.expense.id]))

		self.assertEqual(response.status_code, 302)
		self.assertTrue(Expense.objects.filter(id=self.expense.id).exists())

	def test_edit_expense_denies_non_manager_user(self):
		self.client.login(username='worker-exp', password='pass1234')

		response = self.client.post(
			reverse('expenses:edit_expense', args=[self.expense.id]),
			data={
				'date': timezone.now().date().isoformat(),
				'category': 'fuel',
				'description': 'Edited by worker',
				'amount': '250.00',
				'payment_mode': 'upi',
			},
		)

		self.assertEqual(response.status_code, 403)
		self.expense.refresh_from_db()
		self.assertEqual(self.expense.description, 'Diesel refill')

	def test_delete_expense_allows_manager_user(self):
		self.client.login(username='manager-exp', password='pass1234')

		response = self.client.post(reverse('expenses:delete_expense', args=[self.expense.id]))

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Expense.objects.filter(id=self.expense.id).exists())

	def test_delete_expense_get_returns_method_not_allowed(self):
		self.client.login(username='manager-exp', password='pass1234')

		response = self.client.get(reverse('expenses:delete_expense', args=[self.expense.id]))

		self.assertEqual(response.status_code, 405)
		self.assertTrue(Expense.objects.filter(id=self.expense.id).exists())
