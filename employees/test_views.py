import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.test import Client

@pytest.mark.django_db
class TestEmployeeViews:
    def setup_method(self):
        self.client = Client()
        # Create a manager user
        self.user = User.objects.create_user(username='manager_user', password='pass123')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.user.groups.add(manager_group)
        
        # Log in the client
        self.client.login(username='manager_user', password='pass123')

    def test_employee_list_view(self):
        """Verify the employee directory loads correctly."""
        # Using the name found in show_urls: 'employee_list'
        url = reverse('employee_list') 
        response = self.client.get(url)
        assert response.status_code == 200

    def test_employee_create_get(self):
        """Verify the add worker form loads correctly."""
        # Using the name found in show_urls: 'add_employee'
        url = reverse('add_employee') 
        response = self.client.get(url)
        assert response.status_code == 200