"""
CWMS Database Population Script
Populates the database with realistic test data for all models
Run: python populate_database.py
"""

import os
import sys
import django
from datetime import date, datetime, timedelta
from decimal import Decimal
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User, Group
from employees.models import Employee, Role
from attendance.models import Attendance
from payroll.models import MonthlySalary
from expenses.models import Expense
from billing.models import Bill

# Color codes for terminal output
GREEN = '\033[92m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

class DatabasePopulator:
    def __init__(self):
        self.employees_created = 0
        self.attendance_created = 0
        self.payroll_created = 0
        self.expenses_created = 0
        self.bills_created = 0
        
    def header(self, title):
        print(f"\n{BLUE}{BOLD}{'='*60}\n{title}\n{'='*60}{RESET}\n")
        
    def success(self, msg):
        print(f"{GREEN}✓ {msg}{RESET}")
        
    def warning(self, msg):
        print(f"{YELLOW}⚠ {msg}{RESET}")
        
    def create_users(self):
        """Create manager and king users"""
        self.header("Creating Users")
        
        # Manager user
        if not User.objects.filter(username='manager').exists():
            manager = User.objects.create_user(
                username='manager',
                email='manager@cwms.local',
                password='password123',
                first_name='Project',
                last_name='Manager'
            )
            # Add to managers group
            managers_group, _ = Group.objects.get_or_create(name='managers')
            manager.groups.add(managers_group)
            self.success(f"Created manager user: {manager.username}")
        else:
            self.warning("Manager user already exists")
        
        # King user
        if not User.objects.filter(username='king').exists():
            king = User.objects.create_user(
                username='king',
                email='owner@cwms.local',
                password='password123',
                first_name='Project',
                last_name='Owner'
            )
            # Add to kings group
            kings_group, _ = Group.objects.get_or_create(name='kings')
            king.groups.add(kings_group)
            self.success(f"Created king user: {king.username}")
        else:
            self.warning("King user already exists")
    
    def create_employees(self):
        """Create sample employees"""
        self.header("Creating Employees")
        
        # First, create or get a default role
        default_role, created = Role.objects.get_or_create(
            name='Worker',
            defaults={'overtime_rate_per_hour': Decimal('75.00')}
        )
        if created:
            self.success(f"Created default role: {default_role.name}")
        
        employee_data = [
            {'username': 'emp_raj', 'name': 'Raj Kumar', 'email': 'raj.kumar@cwms.local', 'phone_number': '9876543210'},
            {'username': 'emp_priya', 'name': 'Priya Singh', 'email': 'priya.singh@cwms.local', 'phone_number': '9876543211'},
            {'username': 'emp_amit', 'name': 'Amit Patel', 'email': 'amit.patel@cwms.local', 'phone_number': '9876543212'},
            {'username': 'emp_deepika', 'name': 'Deepika Verma', 'email': 'deepika.verma@cwms.local', 'phone_number': '9876543213'},
            {'username': 'emp_vikram', 'name': 'Vikram Sharma', 'email': 'vikram.sharma@cwms.local', 'phone_number': '9876543214'},
            {'username': 'emp_nisha', 'name': 'Nisha Gupta', 'email': 'nisha.gupta@cwms.local', 'phone_number': '9876543215'},
            {'username': 'emp_arjun', 'name': 'Arjun Reddy', 'email': 'arjun.reddy@cwms.local', 'phone_number': '9876543216'},
            {'username': 'emp_isha', 'name': 'Isha Malhotra', 'email': 'isha.malhotra@cwms.local', 'phone_number': '9876543217'},
            {'username': 'emp_rohan', 'name': 'Rohan Das', 'email': 'rohan.das@cwms.local', 'phone_number': '9876543218'},
            {'username': 'emp_zara', 'name': 'Zara Khan', 'email': 'zara.khan@cwms.local', 'phone_number': '9876543219'},
        ]
        
        for emp_data in employee_data:
            username = emp_data.pop('username')
            
            # Create user if doesn't exist
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    email=emp_data['email'],
                    password='password123',
                    first_name=emp_data['name'].split()[0],
                    last_name=emp_data['name'].split()[-1]
                )
            else:
                user = User.objects.get(username=username)
            
            # Create employee if doesn't exist
            if not Employee.objects.filter(user=user).exists():
                emp = Employee.objects.create(
                    user=user,
                    name=emp_data['name'],
                    email=emp_data['email'],
                    phone_number=emp_data['phone_number'],
                    role=default_role,
                    daily_wage=Decimal('500.00'),
                    join_date=date.today() - timedelta(days=random.randint(30, 365))
                )
                self.employees_created += 1
                self.success(f"Created employee: {emp.name}")
            else:
                self.warning(f"Employee user {username} already exists")
    
    def create_attendance(self):
        """Create sample attendance records for the last 30 days"""
        self.header("Creating Attendance Records")
        
        employees = Employee.objects.all()
        if not employees.exists():
            self.warning("No employees found. Skipping attendance creation.")
            return
        
        status_choices = ['P', 'H', 'A']  # Present, Half-day, Absent
        
        for emp in employees:
            for i in range(30):
                att_date = date.today() - timedelta(days=i)
                
                # Skip weekends (Saturday=5, Sunday=6)
                if att_date.weekday() >= 5:
                    continue
                
                if not Attendance.objects.filter(employee=emp, date=att_date).exists():
                    status = random.choices(
                        status_choices,
                        weights=[70, 15, 15]  # 70% present, 15% half-day, 15% absent
                    )[0]
                    
                    overtime = Decimal('0.00')
                    if status == 'P':
                        overtime = Decimal(random.uniform(0, 3))
                    
                    att = Attendance.objects.create(
                        employee=emp,
                        date=att_date,
                        status=status,
                        overtime_hours=Decimal(str(round(overtime, 2)))
                    )
                    self.attendance_created += 1
        
        self.success(f"Created {self.attendance_created} attendance records")
    
    def create_payroll(self):
        """Create sample payroll records for the last 3 months"""
        self.header("Creating Payroll Records")
        
        employees = Employee.objects.all()
        if not employees.exists():
            self.warning("No employees found. Skipping payroll creation.")
            return
        
        for emp in employees:
            for month_offset in range(3):
                # Calculate month for payroll
                month_date = date.today().replace(day=1) - timedelta(days=30 * month_offset)
                month_date = month_date.replace(day=1)
                
                if not MonthlySalary.objects.filter(employee=emp, month=month_date).exists():
                    # Get attendance data for this month
                    att_records = Attendance.objects.filter(
                        employee=emp,
                        date__month=month_date.month,
                        date__year=month_date.year
                    )
                    
                    days_present = att_records.filter(status='P').count()
                    half_days = att_records.filter(status='H').count()
                    overtime_hours = att_records.aggregate(
                        total=django.db.models.Sum('overtime_hours')
                    )['total'] or Decimal('0.00')
                    
                    # Base salary calculation
                    base_daily_rate = Decimal('500.00')
                    gross_pay = (
                        (days_present * base_daily_rate) +
                        (half_days * base_daily_rate / 2) +
                        (overtime_hours * Decimal('75.00'))
                    )
                    
                    # Deductions
                    advance_deducted = Decimal('0.00')
                    if random.random() > 0.7:  # 30% chance of advance
                        advance_deducted = Decimal(random.randint(1000, 3000))
                    
                    net_pay = gross_pay - advance_deducted
                    
                    salary = MonthlySalary.objects.create(
                        employee=emp,
                        month=month_date,
                        days_present=days_present,
                        half_days=half_days,
                        paid_leaves=0,
                        overtime_hours=overtime_hours,
                        gross_pay=gross_pay,
                        advance_deducted=advance_deducted,
                        net_pay=net_pay,
                        remaining_advance=Decimal('0.00'),
                        is_paid=random.random() > 0.3  # 70% paid, 30% pending
                    )
                    
                    if salary.is_paid:
                        salary.paid_on = date.today()
                        salary.save()
                    
                    self.payroll_created += 1
        
        self.success(f"Created {self.payroll_created} payroll records")
    
    def create_expenses(self):
        """Create sample expense records"""
        self.header("Creating Expense Records")
        
        manager = User.objects.filter(username='manager').first()
        if not manager:
            self.warning("Manager user not found. Skipping expenses.")
            return
        
        expense_categories = [
            'Materials', 'Labor', 'Equipment', 'Transport',
            'Tools', 'Safety', 'Other'
        ]
        
        payment_modes = ['Cash', 'Bank Transfer', 'Cheque', 'Card']
        
        for i in range(25):
            expense = Expense.objects.create(
                description=f"Expense Item {i+1}",
                category=random.choice(expense_categories),
                amount=Decimal(str(random.randint(500, 10000))),
                date=date.today() - timedelta(days=random.randint(0, 30)),
                payment_mode=random.choice(payment_modes),
                created_by=manager
            )
            self.expenses_created += 1
        
        self.success(f"Created {self.expenses_created} expense records")
    
    def create_bills(self):
        """Create sample bill records"""
        self.header("Creating Bill Records")
        
        for i in range(10):
            bill = Bill.objects.create(
                description=f"Bill #{i+1000}",
                amount=Decimal(str(random.randint(5000, 50000))),
                is_paid=random.random() > 0.4,  # 60% paid, 40% pending
                pdf_file=None
            )
            
            if bill.is_paid:
                bill.paid_on = date.today() - timedelta(days=random.randint(0, 15))
                bill.save()
            
            self.bills_created += 1
        
        self.success(f"Created {self.bills_created} bill records")
    
    def run(self):
        """Run all population steps"""
        print(f"\n{BOLD}{BLUE}CWMS DATABASE POPULATION SCRIPT{RESET}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        try:
            self.create_users()
            self.create_employees()
            self.create_attendance()
            self.create_payroll()
            self.create_expenses()
            self.create_bills()
            
            # Summary
            self.header("Population Summary")
            print(f"Employees: {self.employees_created}")
            print(f"Attendance Records: {self.attendance_created}")
            print(f"Payroll Records: {self.payroll_created}")
            print(f"Expense Records: {self.expenses_created}")
            print(f"Bill Records: {self.bills_created}")
            print(f"\n{GREEN}{BOLD}✓ Database population completed successfully!{RESET}\n")
            
        except Exception as e:
            print(f"\n{YELLOW}Error during population: {str(e)}{RESET}\n")
            raise

if __name__ == '__main__':
    import django.db.models
    populator = DatabasePopulator()
    populator.run()
