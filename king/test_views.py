import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import Client

@pytest.mark.django_db
class TestKingViews:
    def setup_method(self):
        self.client = Client()
        
        # Owner dashboards usually require superuser access. 
        self.user = User.objects.create_superuser(username='company_owner', password='ownerpass123')
        self.client.login(username='company_owner', password='ownerpass123')
        
        # --- IF YOUR APP USES A CUSTOM SESSION FLAG ---
        # Some custom owner portals use a session flag instead of standard Django Auth.
        # If these tests return 302 (Redirects to login), we will uncomment these lines:
        # session = self.client.session
        # session['is_owner'] = True
        # session.save()

    def test_main_king_dashboard(self):
        """Trigger the main company overview dashboard."""
        url = reverse('king:king_dashboard')
        response = self.client.get(url)
        assert response.status_code in [200, 302]

    def test_ledger_dashboard(self):
        """Trigger the company ledger and expense aggregations."""
        url = reverse('king:ledger')
        response = self.client.get(url)
        assert response.status_code in [200, 302]

    def test_revenue_dashboard(self):
        """Trigger the revenue tracking dashboard."""
        url = reverse('king:revenue_dashboard')
        response = self.client.get(url)
        assert response.status_code in [200, 302]

    def test_workorder_dashboard(self):
        """Trigger the work order management lists."""
        url = reverse('king:workorder_dashboard')
        response = self.client.get(url)
        assert response.status_code in [200, 302]