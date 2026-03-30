from decimal import Decimal

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
