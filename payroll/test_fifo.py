import pytest
from decimal import Decimal
from django.contrib.auth.models import User
from employees.models import Employee
from payroll.models import Advance
from payroll.services import generate_monthly_salary
from datetime import date
from attendance.models import Attendance


@pytest.mark.django_db
class TestFIFOAdvanceDeduction:
    
    def setup_method(self):
        """Create test employee with advances"""
        from employees.models import Role
        
        self.user = User.objects.create_user(
            username='test_worker',
            password='testpass123'
        )
        self.role = Role.objects.create(
            name='Test Role',
            overtime_rate_per_hour=Decimal('50.00'),
            is_active=True
        )
        self.employee = Employee.objects.create(
            user=self.user,
            name='Test Worker',
            phone_number='9999999999',
            role=self.role,
            daily_wage=Decimal('500.00'),
            is_active=True,
            join_date=date(2026, 1, 1)
        )

    def test_oldest_advance_deducted_first(self):
        """FIFO: January advance must be deducted before February advance"""
        
        # 1. Force the worker to have a valid daily wage so they earn money!
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()

        # Create two advances in order (explicitly marking them unsettled)
        jan_advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            issued_date=date(2026, 1, 15),
            remaining_amount=Decimal('1000.00'),
            settled=False # Force flag
        )
        feb_advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('2000.00'),
            issued_date=date(2026, 2, 10),
            remaining_amount=Decimal('2000.00'),
            settled=False # Force flag
        )

        # Bypass the .clean() temporal rules using bulk_create
        attendances = [
            Attendance(
                employee=self.employee,
                date=date(2026, 3, day),
                status='P'
            )
            for day in range(1, 11)
        ]
        Attendance.objects.bulk_create(attendances)

        # Generate March salary
        salary = generate_monthly_salary(
            self.employee,
            date(2026, 3, 1)
        )

        # DIAGNOSTIC CHECK: Let's prove the worker actually generated earnings
        assert salary.gross_pay > Decimal('0.00'), \
            f"Gross pay is 0! Attendance wasn't counted. Salary data: {salary.__dict__}"

        # Refresh from DB
        jan_advance.refresh_from_db()
        feb_advance.refresh_from_db()

        # January advance must be touched first
        assert jan_advance.remaining_amount < Decimal('1000.00'), \
            "FIFO failed: January advance was not deducted first"

    def test_advance_fully_recovered_before_next(self):
        """January advance fully recovered before touching February"""

        # 1. Force the worker to have a valid daily wage so they earn money!
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()
        
        jan_advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            issued_date=date(2026, 1, 15),
            remaining_amount=Decimal('1000.00'),
            settled=False
        )
        
        feb_advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('5000.00'),
            issued_date=date(2026, 2, 10),
            remaining_amount=Decimal('5000.00'),
            settled=False
        )

        # Bypass the .clean() temporal rules using bulk_create
        attendances = [
            Attendance(
                employee=self.employee,
                date=date(2026, 3, day),
                status='P'
            )
            for day in range(1, 11)
        ]
        Attendance.objects.bulk_create(attendances)

        # Generate March salary
        salary = generate_monthly_salary(
            self.employee,
            date(2026, 3, 1)
        )

        assert salary.gross_pay > Decimal('0.00'), \
            f"Gross pay is 0! Attendance wasn't counted. Salary data: {salary.__dict__}"
        
        # Refresh from DB
        jan_advance.refresh_from_db()
        feb_advance.refresh_from_db()

        # Because the worker made 10,000 (10 days * 1000), the 1000 advance should be fully wiped out
        assert jan_advance.remaining_amount == Decimal('0.00'), \
            "FIFO failed: January advance was not completely settled"

    def test_no_negative_advance_balance(self):
        """Advance remaining_amount should never go below zero"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('100.00'),
            issued_date=date(2026, 1, 15),
            remaining_amount=Decimal('100.00')
        )

        # We need to give them attendance here too, otherwise the balance won't change at all!
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()
        attendances = [
            Attendance(employee=self.employee, date=date(2026, 3, day), status='P')
            for day in range(1, 11)
        ]
        Attendance.objects.bulk_create(attendances)

        generate_monthly_salary(self.employee, date(2026, 3, 1))
        advance.refresh_from_db()

        assert advance.remaining_amount >= Decimal('0.00'), \
            "Advance remaining_amount went negative"
    

    def test_partial_advance_recovery(self):
        """EDGE CASE 1: Worker doesn't earn enough to cover the whole advance."""
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()
        
        # Owe 2000
        advance = Advance.objects.create(
            employee=self.employee, amount=Decimal('2000.00'),
            issued_date=date(2026, 1, 15), remaining_amount=Decimal('2000.00'), settled=False
        )

        # Work only 1 day = Earn 1000
        # (We can use create() here because we are only adding one day, but let's stick to bulk_create just in case)
        Attendance.objects.bulk_create([
            Attendance(employee=self.employee, date=date(2026, 3, 1), status='P')
        ])

        generate_monthly_salary(self.employee, date(2026, 3, 1))
        advance.refresh_from_db()

        # The advance should have exactly 1000 left over, and NOT be settled
        assert advance.remaining_amount == Decimal('1000.00'), f"Partial deduction failed. Remaining is {advance.remaining_amount}"
        assert advance.settled is False, "Advance was marked settled prematurely!"

    def test_exact_change_recovery(self):
        """EDGE CASE 2: Worker earns exactly what they owe."""
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()

        # Owe 1000
        advance = Advance.objects.create(
            employee=self.employee, amount=Decimal('1000.00'),
            issued_date=date(2026, 1, 15), remaining_amount=Decimal('1000.00'), settled=False
        )

        # Work 1 day = Earn 1000
        Attendance.objects.bulk_create([
            Attendance(employee=self.employee, date=date(2026, 3, 1), status='P')
        ])

        generate_monthly_salary(self.employee, date(2026, 3, 1))
        advance.refresh_from_db()

        assert advance.remaining_amount == Decimal('0.00'), "Should wipe out exactly to 0"
        assert advance.settled is True, "Should be marked settled"

    def test_multiple_small_advances_wipeout(self):
        """EDGE CASE 3: Worker has several small advances, earns enough to wipe all of them out."""
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()

        # Total debt = 1000 spread across 3 advances
        adv1 = Advance.objects.create(employee=self.employee, amount=Decimal('200.00'), issued_date=date(2026, 1, 10), remaining_amount=Decimal('200.00'), settled=False)
        adv2 = Advance.objects.create(employee=self.employee, amount=Decimal('300.00'), issued_date=date(2026, 1, 15), remaining_amount=Decimal('300.00'), settled=False)
        adv3 = Advance.objects.create(employee=self.employee, amount=Decimal('500.00'), issued_date=date(2026, 2, 10), remaining_amount=Decimal('500.00'), settled=False)

        # Work 2 days = Earn 2000
        attendances = [Attendance(employee=self.employee, date=date(2026, 3, day), status='P') for day in range(1, 3)]
        Attendance.objects.bulk_create(attendances)

        generate_monthly_salary(self.employee, date(2026, 3, 1))

        adv1.refresh_from_db()
        adv2.refresh_from_db()
        adv3.refresh_from_db()

        assert adv1.remaining_amount == Decimal('0.00') and adv1.settled is True, "Adv1 not cleared"
        assert adv2.remaining_amount == Decimal('0.00') and adv2.settled is True, "Adv2 not cleared"
        assert adv3.remaining_amount == Decimal('0.00') and adv3.settled is True, "Adv3 not cleared"

    def test_ghost_worker_zero_pay(self):
        """EDGE CASE 4: Worker has debt but 0 attendance. System should safely skip them."""
        self.employee.daily_wage = Decimal('1000.00')
        self.employee.save()

        # Owe 1000
        advance = Advance.objects.create(
            employee=self.employee, amount=Decimal('1000.00'),
            issued_date=date(2026, 1, 15), remaining_amount=Decimal('1000.00'), settled=False
        )

        # NO ATTENDANCE CREATED (Gross pay = 0)

        generate_monthly_salary(self.employee, date(2026, 3, 1))
        advance.refresh_from_db()

        assert advance.remaining_amount == Decimal('1000.00'), "Advance was deducted from ghost worker!"
        assert advance.settled is False, "Advance was marked settled for ghost worker!"