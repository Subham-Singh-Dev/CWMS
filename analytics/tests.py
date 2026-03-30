from django.contrib.auth.models import Group, User
from django.test import RequestFactory, TestCase

from analytics.models import AuditLog
from analytics.services.audit_service import create_audit_log, infer_user_role


class AuditServiceTests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.king_group, _ = Group.objects.get_or_create(name='King')
		self.manager_group, _ = Group.objects.get_or_create(name='Manager')

	def test_infer_user_role_for_superuser_is_king(self):
		user = User.objects.create_user(username='admin', password='pass1234', is_superuser=True)
		self.assertEqual(infer_user_role(user), 'King')

	def test_infer_user_role_for_manager_group(self):
		user = User.objects.create_user(username='mgr', password='pass1234')
		user.groups.add(self.manager_group)

		self.assertEqual(infer_user_role(user), 'Manager')

	def test_create_audit_log_uses_forwarded_ip(self):
		user = User.objects.create_user(username='king1', password='pass1234')
		user.groups.add(self.king_group)
		request = self.factory.get('/', HTTP_X_FORWARDED_FOR='203.0.113.5, 10.0.0.1')

		log = create_audit_log(
			user=user,
			username=user.username,
			activity='attendance',
			action='mark_present',
			entity_type='Attendance',
			entity_id=1,
			entity_name='Worker - 2025-01-01',
			details='Status: present',
			request=request,
		)

		self.assertEqual(log.username, 'king1')
		self.assertEqual(log.user_role, 'King')
		self.assertEqual(log.ip_address, '203.0.113.5')
		self.assertEqual(AuditLog.objects.count(), 1)

	def test_create_audit_log_defaults_username_for_system(self):
		request = self.factory.get('/', REMOTE_ADDR='127.0.0.1')

		log = create_audit_log(
			user=None,
			username='',
			activity='system',
			action='other',
			entity_type='System',
			entity_id=0,
			entity_name='HealthCheck',
			details='Startup complete',
			request=request,
		)

		self.assertEqual(log.username, 'SYSTEM')
		self.assertEqual(log.user_role, 'System')
		self.assertEqual(log.ip_address, '127.0.0.1')
