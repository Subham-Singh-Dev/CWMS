import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone

from employees.models import Employee, Role
from attendance.models import Attendance
from leaves.models import LeavePolicy
from leaves.services import assign_leave
from payroll.models import MonthlySalary
from payroll.services import generate_monthly_salary

# ====================================================================
# FIXTURES: Setting up the sandbox environment
# ====================================================================

@pytest.fixture
def setup_data(db):
    """Creates base data: User, Role, Employee, and Leave Policy."""
    # 1. Create Base Requirements
    user = User.objects.create_user(username="test_worker", password="password")
    role = Role.objects.create(name="Mason", overtime_rate_per_hour=Decimal('100.00'))
    
    # 2. Create the Employee (Daily Wage: ₹500, Permanent)
    employee = Employee.objects.create(
        user=user,
        name="Raj Kumar",
        phone_number="9999999999",
        role=role,
        daily_wage=Decimal('500.00'),
        employment_type='PERMANENT',
        join_date=date(2025, 1, 1),
        is_active=True,
        pf_applicable=False,
        esic_applicable=False
    )
    
    # 3. Create the Leave Policy
    LeavePolicy.objects.create(employment_type='PERMANENT', annual_leave_days=30)
    
    # Return a dictionary so tests can easily access the instances
    return {
        'admin': User.objects.create_superuser(username="admin", password="password"),
        'employee': employee,
    }


# ====================================================================
# PHASE 3: The Payroll Math Test
# ====================================================================

@pytest.mark.django_db
def test_hybrid_month_payroll_math(setup_data):
    """
    Test 7 & 8: Verifies that Leaves ('L') are paid and Absents ('A') are unpaid.
    Scenario: 3 Present, 2 Approved Leaves, 1 Absent. 
    Expected Gross Pay: ₹2500 (5 paid days * 500)
    """
    employee = setup_data['employee']
    target_month = date(2026, 5, 1) # First day of May
    
    # 1. Manually mark 3 'P' and 1 'A' in the database
    Attendance.objects.create(employee=employee, date=date(2026, 5, 1), status='P')
    Attendance.objects.create(employee=employee, date=date(2026, 5, 2), status='P')
    Attendance.objects.create(employee=employee, date=date(2026, 5, 3), status='P')
    Attendance.objects.create(employee=employee, date=date(2026, 5, 4), status='A')
    
    # 2. Use the Service to assign 2 days of formal Leave
    assign_leave(
        employee=employee,
        leave_type='CL',
        from_date=date(2026, 5, 5),
        to_date=date(2026, 5, 6),
        total_days=2,
        reason="Family event",
        address_on_leave="",
        application_date=timezone.now().date(),
        approved_by=setup_data['admin']
    )
    
    # 3. Run the Payroll Generation Engine
    salary_slip = generate_monthly_salary(employee, target_month)
    
    # 4. Assertions (The strict mathematical checks)
    assert salary_slip is not None, "Salary should have been generated."
    assert salary_slip.days_present == 3, "Should count exactly 3 present days."
    assert salary_slip.paid_leaves == 2, "Should count exactly 2 paid leave days."
    
    # Financial Assertions: 5 paid days * 500 = 2500
    assert salary_slip.gross_pay == Decimal('2500.00'), f"Expected 2500.00, got {salary_slip.gross_pay}"
    assert salary_slip.net_pay == Decimal('2500.00'), "Net pay should match gross if no deductions exist."


# ====================================================================
# PHASE 4: The Closed Financial Period Test
# ====================================================================

@pytest.mark.django_db
def test_cannot_assign_leave_in_paid_month(setup_data):
    """
    Test 9: Verifies that the system blocks leave assignments 
    if the salary for that month is already marked as 'Paid'.
    """
    employee = setup_data['employee']
    paid_month = date(2026, 4, 1) # April
    
    # 1. Create a "Paid" salary record for April
    MonthlySalary.objects.create(
        employee=employee,
        month=paid_month,
        days_present=20,
        gross_pay=Decimal('10000.00'),
        net_pay=Decimal('10000.00'),
        is_paid=True, # <--- THE CRITICAL FLAG
        paid_on=timezone.now().date()
    )
    
    # 2. Attempt to assign leave in the middle of April
    # We use pytest.raises to prove that the ValidationError is correctly thrown
    with pytest.raises(ValidationError) as excinfo:
        assign_leave(
            employee=employee,
            leave_type='SL',
            from_date=date(2026, 4, 10),
            to_date=date(2026, 4, 12),
            total_days=3,
            reason="Sick",
            address_on_leave="",
            application_date=timezone.now().date(),
            approved_by=setup_data['admin']
        )
    
    # 3. Verify the error message matches your strict architecture
    assert "already paid" in str(excinfo.value)
    assert "Cannot assign leave" in str(excinfo.value)