import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from employees.models import Employee, Role

@pytest.fixture
def manager_client(db):
    """
    Creates a manager user and returns an authenticated DRF APIClient.
    """
    user = User.objects.create_user(
        username='test_manager', 
        password='password123',
        is_staff=True 
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def employee(db):
    """
    Provides a saved Employee instance for testing CRUD operations.
    Aligned with the CWMS Employee model fields.
    """
    # 1. Create the Auth User required by the OneToOneField
    user = User.objects.create_user(username='worker_profile_user', password='password123')
    
    # 2. Create the Role required by the ForeignKey
    test_role, _ = Role.objects.get_or_create(
        name="Laborer",
        defaults={
            'overtime_rate_per_hour': Decimal('150.00') 
        }
    )
    
    # 3. Create the Employee instance with correct field names
    return Employee.objects.create(
        user=user,
        name="Test Worker",
        phone_number="9123456789",
        role=test_role,
        daily_wage=Decimal('550.50'),
        employment_type='LOCAL',
        join_date=timezone.now().date(),
        is_active=True
    )