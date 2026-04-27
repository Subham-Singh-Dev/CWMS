import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse


@pytest.mark.django_db
class TestRBACDecorators:

    def setup_method(self):
        self.client = Client()
        
        # Create groups
        self.manager_group = Group.objects.create(name='Manager')
        self.worker_group = Group.objects.create(name='Worker')
        self.king_group = Group.objects.create(name='King')

        # Create users
        self.manager_user = User.objects.create_user(
            username='manager1', password='pass123'
        )
        self.manager_user.groups.add(self.manager_group)

        self.worker_user = User.objects.create_user(
            username='worker1', password='pass123'
        )
        self.worker_user.groups.add(self.worker_group)

    def test_manager_can_access_dashboard(self):
        self.client.login(username='manager1', password='pass123')
        response = self.client.get(reverse('manager_dashboard'))
        assert response.status_code == 200

    def test_worker_cannot_access_manager_dashboard(self):
        self.client.login(username='worker1', password='pass123')
        response = self.client.get(reverse('manager_dashboard'))
        assert response.status_code in [302, 403]

    def test_unauthenticated_redirected_to_login(self):
        response = self.client.get(reverse('manager_dashboard'))
        assert response.status_code == 302
        assert 'login' in response.url

    def test_manager_cannot_access_king_dashboard(self):
        """A normal manager should be blocked from the King's dashboard."""
        self.client.login(username='manager', password='testpass123')
        
        # Attempt to access a king-only route
        response = self.client.get('/king/dashboard/')
        
        # Should redirect to the King login page, NOT let them in
        assert response.status_code == 302
        assert '/king/secure/' in response.url

    def test_king_can_access_king_dashboard(self):
        """The King with the proper session flag and group can access the dashboard."""
        
        # 1. Create a pure, dedicated King user (NO manager ties)
        from django.contrib.auth.models import User, Group
        king_user = User.objects.create_user(username='actual_king', password='kingpass123')
        
        # 2. Add them strictly to the King group
        king_group, _ = Group.objects.get_or_create(name='King')
        king_user.groups.add(king_group)

        # 3. Log them in
        self.client.login(username='actual_king', password='kingpass123')
        
        # 4. Manually set the strict king_authenticated session flag
        session = self.client.session
        session['king_authenticated'] = True
        session.save()

        # 5. Attempt to access the King dashboard
        response = self.client.get('/king/dashboard/')

        # 6. Should successfully load the page (200 OK)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. User was redirected or forbidden."
    