import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.test import Client
from employees.models import Employee, Role
from decimal import Decimal
from datetime import date

@pytest.mark.django_db
class TestPayrollViews:
    def setup_method(self):
        self.client = Client()
        
        # 1. Setup Manager User
        self.user = User.objects.create_user(username='payroll_mgr', password='pass123')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.user.groups.add(manager_group)
        
        # 2. Login
        self.client.login(username='payroll_mgr', password='pass123')
        
        # 3. Setup a dummy employee so the lists aren't empty
        self.role = Role.objects.create(name='Worker', overtime_rate_per_hour=Decimal('50'), is_active=True)
        self.employee = Employee.objects.create(
            user=self.user,
            name='Test Worker', 
            phone_number='9998887776',
            daily_wage=Decimal('1000'), 
            role=self.role,
            employment_type='Permanent',
            pf_applicable=True,
            esic_applicable=True,
            join_date=date(2026, 1, 1),
            is_active=True
        )

    def test_salary_list_view(self):
        """Trigger the main salary dashboard."""
        # Using the exact name from show_urls
        url = reverse('manager_salary_list') 
        response = self.client.get(url)
        # Checking for 200 (OK) or 302 (Redirect, common if logic pushes you to a specific month)
        assert response.status_code in [200, 302]

    def test_generate_payroll_post(self):
        """Trigger the 'Generate Payroll' view with exact validation requirements."""
        from attendance.models import Attendance
        
        # 1. Setup Attendance so the view doesn't return 'None' for the salary
        attendances = [
            Attendance(employee=self.employee, date=date(2026, 4, day), status='P')
            for day in range(1, 21)
        ]
        Attendance.objects.bulk_create(attendances)
        
        # 2. The EXACT payload your view demands
        url = reverse('generate_employee_salary')
        payload = {
            'employee_id': self.employee.id,
            'month': '2026-04'  # MUST be YYYY-MM format to pass the strptime check!
        }
        
        # 3. Execute POST
        response = self.client.post(url, data=payload)
        
        # 4. Verify Success (It returns a 302 Redirect to the salary list on success)
        assert response.status_code in [200, 302]
    def test_payroll_batch_summary_get(self):
        """Trigger the massive payroll batch summary dashboard to unlock aggregation logic."""
        from payroll.models import MonthlySalary
        
        # 1. Create a dummy generated salary so the chart logic actually runs!
        # If the database is empty, the view skips the math. We want it to do the math.
        MonthlySalary.objects.create(
            employee=self.employee,
            month=date.today().replace(day=1),
            days_present=20,
            half_days=0,
            overtime_hours=Decimal('0.0'),
            gross_pay=Decimal('20000.00'),
            advance_deducted=Decimal('0.00'),
            pf_deduction=Decimal('2400.00'),
            esic_deduction=Decimal('150.00'),
            net_pay=Decimal('17450.00'),
            is_paid=False
        )
        
        # 2. Load the dashboard (using the exact name from your show_urls)
        url = reverse('payroll_batch_summary')
        response = self.client.get(url)
        
        # 3. Verify it renders without crashing
        assert response.status_code == 200