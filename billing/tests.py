from decimal import Decimal
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from billing.models import Bill


class BillingFlowTests(TestCase):
	def setUp(self):
		self.manager_group, _ = Group.objects.get_or_create(name='Manager')
		self.user = User.objects.create_user(username='manager2', password='pass1234')
		self.user.groups.add(self.manager_group)
		self.client.login(username='manager2', password='pass1234')

	def test_billing_dashboard_post_creates_bill(self):
		pdf = SimpleUploadedFile('invoice.pdf', b'%PDF-1.4 test content', content_type='application/pdf')

		response = self.client.post(
			reverse('billing:billing_dashboard'),
			data={
				'description': 'Diesel Purchase',
				'amount': '1200.50',
				'pdf_file': pdf,
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Bill.objects.count(), 1)
		bill = Bill.objects.first()
		self.assertEqual(bill.description, 'Diesel Purchase')
		self.assertEqual(bill.amount, Decimal('1200.50'))
		self.assertFalse(bill.is_paid)

	def test_billing_dashboard_post_missing_file_rejects_request(self):
		response = self.client.post(
			reverse('billing:billing_dashboard'),
			data={
				'description': 'Office Supplies',
				'amount': '499.99',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Bill.objects.count(), 0)

	def test_toggle_bill_status_requires_login(self):
		bill = Bill.objects.create(description='Raw Material', amount=Decimal('100.00'))
		self.client.logout()

		response = self.client.post(reverse('billing:toggle_bill_status', args=[bill.id]))

		self.assertEqual(response.status_code, 302)
		bill.refresh_from_db()
		self.assertFalse(bill.is_paid)

	def test_toggle_bill_status_denies_non_manager_user(self):
		bill = Bill.objects.create(description='Raw Material', amount=Decimal('100.00'))
		worker = User.objects.create_user(username='worker-no-manager', password='pass1234')
		self.client.logout()
		self.client.login(username='worker-no-manager', password='pass1234')

		response = self.client.post(reverse('billing:toggle_bill_status', args=[bill.id]))

		self.assertEqual(response.status_code, 403)
		bill.refresh_from_db()
		self.assertFalse(bill.is_paid)

	def test_delete_bill_denies_non_manager_user(self):
		bill = Bill.objects.create(description='Machine Repair', amount=Decimal('500.00'))
		worker = User.objects.create_user(username='worker-delete', password='pass1234')
		self.client.logout()
		self.client.login(username='worker-delete', password='pass1234')

		response = self.client.post(reverse('billing:delete_bill', args=[bill.id]))

		self.assertEqual(response.status_code, 403)
		self.assertTrue(Bill.objects.filter(id=bill.id).exists())

	def test_mark_bill_paid_uses_selected_date(self):
		bill = Bill.objects.create(description='Office Rent', amount=Decimal('1500.00'))

		response = self.client.post(
			reverse('billing:toggle_bill_status', args=[bill.id]),
			data={'paid_on': '2026-03-31'},
		)

		self.assertEqual(response.status_code, 302)
		bill.refresh_from_db()
		self.assertTrue(bill.is_paid)
		self.assertEqual(bill.paid_on, date(2026, 3, 31))
