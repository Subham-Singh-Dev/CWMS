import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from employees.models import Employee, Role
from attendance.models import Attendance

@pytest.mark.django_db
class TestAttendanceAPI:
    
    def setup_method(self):
        """Set up the test client, user, and employee for API requests."""
        from django.contrib.auth.models import Group
        self.client = APIClient()
        
        # Create a Manager user
        self.user = User.objects.create_user(
            username='api_manager',
            password='testpass123'
        )

        # --- THE FIX: Officially make them a Manager ---
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.user.groups.add(manager_group)
        # -----------------------------------------------
        
        # Create the employee profile linked to the user
        self.role = Role.objects.create(name='Test Role', overtime_rate_per_hour=Decimal('50.00'), is_active=True)
        self.employee = Employee.objects.create(
            user=self.user,
            name='API Worker',
            phone_number='8888888888',
            role=self.role,
            daily_wage=Decimal('600.00'),
            is_active=True,
            join_date=date(2026, 1, 1)
        )
        
        # Define API endpoints based on your routing
        self.token_url = '/api/token/'
        self.attendance_url = '/api/attendance/'

    def get_auth_headers(self):
        """Helper method to get a valid JWT token for requests."""
        response = self.client.post(self.token_url, {
            'username': 'api_manager',
            'password': 'testpass123'
        })
        token = response.data['access']
        return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def test_unauthenticated_request_rejected(self):
        """Ensure the API blocks requests without a JWT token."""
        response = self.client.get(self.attendance_url)
        # 401 Unauthorized
        assert response.status_code == 401

    def test_mark_attendance_success(self):
        """Ensure a valid authenticated request can mark attendance."""
        headers = self.get_auth_headers()
        today = timezone.now().date()
        
        payload = {
            'employee': self.employee.id,
            'date': today.strftime('%Y-%m-%d'),
            'status': 'P',  # Present
            'overtime_hours': 0
        }
        
        response = self.client.post(self.attendance_url, data=payload, **headers)
        
        # 201 Created
        assert response.status_code == 201
        
        # Verify it actually hit the database
        assert Attendance.objects.filter(employee=self.employee, date=today, status='P').exists()

    def test_get_attendance_for_date(self):
        """Ensure we can fetch attendance records for a specific date."""
        headers = self.get_auth_headers()
        today = timezone.now().date()
        
        # Pre-populate an attendance record
        Attendance.objects.create(employee=self.employee, date=today, status='H') # Half Day
        
        # Hit the GET endpoint with a query parameter
        response = self.client.get(f"{self.attendance_url}?date={today.strftime('%Y-%m-%d')}", **headers)
        
        # 200 OK
        assert response.status_code == 200
        
        # THE FIX: Look inside the custom 'attendance' key for the list of records
        data = response.data
        if isinstance(data, dict) and 'attendance' in data:
            data_list = data['attendance']
        elif isinstance(data, dict) and 'results' in data:
            data_list = data['results']
        else:
            data_list = data

        # Ensure our record values match
        assert len(data_list) > 0, "The attendance list is empty!"
        
        record = data_list[0]
        assert record.get('status') == 'H', f"Expected status 'H', got {record.get('status')}"
        assert record.get('employee') == self.employee.id

    def test_mark_future_attendance_rejected(self):
        """Ensure the API enforces the 'no future dates' model validation."""
        from django.core.exceptions import ValidationError  # Import the raw Django error
        
        headers = self.get_auth_headers()
        tomorrow = timezone.now().date() + timedelta(days=1)
        
        payload = {
            'employee': self.employee.id,
            'date': tomorrow.strftime('%Y-%m-%d'),
            'status': 'P',
            'overtime_hours': 0
        }
        
        # THE FIX: Tell Pytest that we explicitly expect the API to crash with a ValidationError
        with pytest.raises(ValidationError) as exc_info:
            self.client.post(self.attendance_url, data=payload, **headers)
        
        # Verify the error message inside the crash is the one we wrote for future dates
        assert "future" in str(exc_info.value).lower()