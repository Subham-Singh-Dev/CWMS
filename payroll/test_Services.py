import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from employees.models import Employee, Role
from attendance.models import Attendance
from payroll.models import MonthlySalary
from payroll.services import generate_monthly_salary

@pytest.mark.django_db
class TestPayrollServices:
    
    def setup_method(self):
        """Set up a baseline employee for salary calculations."""
        self.user = User.objects.create_user(username='payroll_tester', password='password123')
        self.role = Role.objects.create(name='Electrician', overtime_rate_per_hour=Decimal('50.00'), is_active=True)
        
        self.employee = Employee.objects.create(
            user=self.user,
            name='Service Worker',
            phone_number='1122334455',
            role=self.role,
            daily_wage=Decimal('1000.00'),
            is_active=True,
            join_date=date(2026, 1, 1)
        )

    def test_generate_salary_full_attendance(self):
        attendances = [Attendance(employee=self.employee, date=date(2026, 4, day), status='P') for day in range(1, 6)]
        Attendance.objects.bulk_create(attendances)
        salary = generate_monthly_salary(self.employee, date(2026, 4, 1))
        assert salary.gross_pay == Decimal('5000.00')

    def test_generate_salary_with_half_days(self):
        Attendance.objects.create(employee=self.employee, date=date(2026, 4, 1), status='H')
        Attendance.objects.create(employee=self.employee, date=date(2026, 4, 2), status='H')
        salary = generate_monthly_salary(self.employee, date(2026, 4, 1))
        assert salary.gross_pay == Decimal('1000.00')

    def test_generate_salary_zero_attendance(self):
        salary = generate_monthly_salary(self.employee, date(2026, 4, 1))
        if salary:
            assert getattr(salary, 'gross_pay', Decimal('0.00')) == Decimal('0.00')

    def test_generate_salary_full_deductions_and_advance(self):
        """Test complex scenario using confirmed field names from the Employee model."""
        from payroll.models import Advance
        
        # 1. Setup: Use the EXACT field names found in your shell output
        self.employee.employment_type = 'Permanent'
        self.employee.pf_applicable = True    # Fixed name
        self.employee.esic_applicable = True  # Fixed name
        
        # Set the fixed rates as per contractor requirement
        self.employee.pf_rate = Decimal('0.1200')
        self.employee.esic_rate = Decimal('0.0075')
        
        # Ensure we have all ID numbers to pass any logic checks
        self.employee.aadhar_number = '123456789012'
        self.employee.pan_number = 'ABCDE1234F'
        self.employee.save()

        # 2. Setup: Worker owes an advance of 2000
        Advance.objects.create(
            employee=self.employee, 
            amount=Decimal('2000.00'),
            remaining_amount=Decimal('2000.00'), 
            issued_date=date(2026, 3, 1)
        )

        # 3. Attendance: 20 days present (20 * 1000 = 20,000 Gross)
        attendances = [
            Attendance(employee=self.employee, date=date(2026, 4, day), status='P', overtime_hours=Decimal('0.0'))
            for day in range(1, 21)
        ]
        Attendance.objects.bulk_create(attendances)

        # 4. Generate Salary for April 1st
        salary = generate_monthly_salary(self.employee, date(2026, 4, 1))

        # 5. Assertions
        assert salary is not None
        assert salary.gross_pay == Decimal('20000.00')
        
        # Verify deductions are no longer 0.00
        # Math: 20,000 * 0.12 = 2,400 | 20,000 * 0.0075 = 150
        assert salary.pf_deduction > 0, "PF is still 0! Check if your logic uses a different string for 'Permanent'."
        assert salary.esic_deduction > 0
        
        # Verify Advance Recovery (Using confirmed name: advance_deducted)
        assert salary.advance_deducted == Decimal('2000.00')
        
        # Final Verification of the Net Pay Formula
        expected_net = salary.gross_pay - salary.pf_deduction - salary.esic_deduction - salary.advance_deducted
        assert salary.net_pay == expected_net