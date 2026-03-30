from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from king.models import LedgerEntry, Revenue, WorkOrder


class KingMutationEndpointTests(TestCase):
	def setUp(self):
		self.king_group, _ = Group.objects.get_or_create(name='King')
		self.manager_group, _ = Group.objects.get_or_create(name='Manager')

		self.king_user = User.objects.create_user(username='owner1', password='pass1234')
		self.king_user.groups.add(self.king_group)

		self.manager_user = User.objects.create_user(username='manager-king', password='pass1234')
		self.manager_user.groups.add(self.manager_group)

		self.workorder = WorkOrder.objects.create(
			client_name='ABC Infra',
			project_name='Plant Expansion',
			location='Pune',
			order_value=Decimal('100000.00'),
			start_date=date.today(),
			end_date=date.today(),
			status='pending',
			created_by=self.king_user,
		)

		self.revenue = Revenue.objects.create(
			date=date.today(),
			amount=Decimal('1000.00'),
			source='Advance',
			category='contract',
			payment_mode='bank',
			created_by=self.king_user,
			work_order=self.workorder,
		)

		self.ledger_entry = LedgerEntry.objects.create(
			date=date.today(),
			entry_type='receipt',
			particulars='Initial balance',
			debit=Decimal('0.00'),
			credit=Decimal('5000.00'),
			created_by=self.king_user,
		)

	def _login_as_king(self):
		self.client.login(username='owner1', password='pass1234')
		session = self.client.session
		session['king_authenticated'] = True
		session.save()

	def test_revenue_delete_get_returns_method_not_allowed(self):
		self._login_as_king()

		response = self.client.get(reverse('king:revenue_delete', args=[self.revenue.id]))

		self.assertEqual(response.status_code, 405)
		self.assertTrue(Revenue.objects.filter(id=self.revenue.id).exists())

	def test_ledger_delete_get_returns_method_not_allowed(self):
		self._login_as_king()

		response = self.client.get(reverse('king:ledger_delete', args=[self.ledger_entry.id]))

		self.assertEqual(response.status_code, 405)
		self.assertTrue(LedgerEntry.objects.filter(id=self.ledger_entry.id).exists())

	def test_workorder_status_update_get_returns_method_not_allowed(self):
		self._login_as_king()

		response = self.client.get(reverse('king:workorder_status_update', args=[self.workorder.id]))

		self.assertEqual(response.status_code, 405)
		self.workorder.refresh_from_db()
		self.assertEqual(self.workorder.status, 'pending')

	def test_revenue_delete_requires_king_access(self):
		response = self.client.post(reverse('king:revenue_delete', args=[self.revenue.id]))
		self.assertEqual(response.status_code, 302)

		self.client.login(username='manager-king', password='pass1234')
		manager_response = self.client.post(reverse('king:revenue_delete', args=[self.revenue.id]))
		self.assertEqual(manager_response.status_code, 302)

		self.assertTrue(Revenue.objects.filter(id=self.revenue.id).exists())

	def test_revenue_delete_post_allows_king(self):
		self._login_as_king()

		response = self.client.post(reverse('king:revenue_delete', args=[self.revenue.id]))

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Revenue.objects.filter(id=self.revenue.id).exists())
