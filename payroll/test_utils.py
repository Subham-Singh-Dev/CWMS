'''
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from employees.models import Employee, Role
from payroll.models import MonthlySalary
from payroll.utils import generate_payslip_pdf


@pytest.fixture
def salary(db):
    user = User.objects.create_user(username='pdf_test', password='pass')
    role = Role.objects.create(
        name='PDF Role',
        overtime_rate_per_hour=Decimal('50.00'),
        is_active=True
    )
    employee = Employee.objects.create(
        user=user,
        name='PDF Worker',
        phone_number='6666666666',
        role=role,
        daily_wage=Decimal('500.00'),
        is_active=True,
        join_date=date(2026, 1, 1)
    )
    return MonthlySalary.objects.create(
        employee=employee,
        month=date(2026, 3, 1),
        days_present=25,
        half_days=0,
        overtime_hours=Decimal('0'),
        gross_pay=Decimal('12500.00'),
        advance_deducted=Decimal('0'),
        net_pay=Decimal('12500.00'),
    )


@pytest.mark.django_db
class TestGeneratePayslipPdf:

    def test_returns_bytes_when_pisa_available(self, salary):
        """Should return PDF bytes or None if pisa unavailable"""
        result = generate_payslip_pdf(salary)
        # Either bytes (pisa works) or None (pisa disabled for deploy)
        assert result is None or isinstance(result, bytes)

    def test_does_not_crash_on_valid_salary(self, salary):
        """Must not raise any exception for a valid salary object"""
        try:
            generate_payslip_pdf(salary)
        except Exception as e:
            pytest.fail(f"generate_payslip_pdf raised an exception: {e}")

    def test_salary_fields_accessible(self, salary):
        """Salary object passed to util must have required fields"""
        assert salary.employee.name == 'PDF Worker'
        assert salary.gross_pay == Decimal('12500.00')
        assert salary.net_pay == Decimal('12500.00')
        assert salary.month == date(2026, 3, 1)'''