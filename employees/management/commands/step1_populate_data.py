"""
Management Command: step1_populate_data
=======================================
Creates:
  - Groups: King, Manager, Worker
  - 1 King (superuser) + 1 Manager user
  - 100 employees (80 LOCAL, 20 PERMANENT) with real Indian names
  - Advances for ~25 employees
  - Leave records for ~15 employees (May 1-5, current month — passes clean())
  - LeavePolicy for LOCAL and PERMANENT

Run:
    docker-compose exec web python manage.py step1_populate_data

Author note: All DB writes go through proper service functions or model
             save() — no raw SQL. Groups created fresh since Docker DB is empty.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from employees.models import Employee, Role
from leaves.models import LeavePolicy
from leaves.services import assign_leave
from payroll.services import issue_advance


# ── Real-world Indian names ──────────────────────────────────────────────────

FIRST_NAMES = [
    "Ramesh", "Suresh", "Mahesh", "Dinesh", "Rajesh", "Naresh", "Ganesh",
    "Mukesh", "Rakesh", "Lokesh", "Umesh", "Yogesh", "Hitesh", "Nilesh",
    "Bhavesh", "Jignesh", "Alpesh", "Dipesh", "Hardik", "Maulik",
    "Sanjay", "Vijay", "Ajay", "Ranjit", "Manjit", "Gurpreet", "Harpreet",
    "Balvinder", "Jaswinder", "Kulwinder", "Amarjit", "Paramjit",
    "Ravi", "Anil", "Sunil", "Kapil", "Sachin", "Vikram", "Rahul", "Rohit",
    "Mohit", "Amit", "Sumit", "Punit", "Ankit", "Nikhil", "Vishal", "Achal",
    "Deepak", "Vivek", "Alok", "Ashok", "Pramod", "Vinod", "Manoj", "Saroj",
    "Santosh", "Ramkumar", "Shivkumar", "Rajkumar", "Arunakumar",
    "Pradeep", "Sandeep", "Kuldeep", "Pardeep", "Mandeep",
    "Girish", "Harish", "Manish", "Jagdish", "Satish", "Devesh",
    "Trilok", "Prahlad", "Subhash", "Prakash", "Brijesh", "Shailesh",
    "Kailash", "Devkumar", "Ramgopal", "Shivdayal", "Hariom", "Omkar",
    "Narayan", "Shravan", "Balram", "Sitaram", "Radhe", "Mohan", "Sohan",
    "Laxman", "Bharat", "Shatrughan", "Dashrath", "Kedar", "Shekhar",
    "Pankaj", "Saurabh", "Gaurav", "Dhruv", "Tanmay", "Pranav",
]

LAST_NAMES = [
    "Kumar", "Singh", "Verma", "Sharma", "Yadav", "Gupta", "Mishra",
    "Tiwari", "Pandey", "Joshi", "Patel", "Shah", "Mehta", "Jain",
    "Agarwal", "Bansal", "Goel", "Mittal", "Saxena", "Srivastava",
    "Chauhan", "Rathore", "Rajput", "Solanki", "Parmar", "Bhatt",
    "Nair", "Pillai", "Menon", "Krishnan", "Iyer", "Rao", "Reddy",
    "Naidu", "Choudhary", "Dubey", "Tripathi", "Shukla", "Upadhyay",
]

# ── Role → (daily_wage_min, daily_wage_max, employment_type) ────────────────

ROLE_CONFIG = {
    "Mason":          (500,  650,  "LOCAL"),
    "Laborer":        (350,  450,  "LOCAL"),
    "Helper":         (300,  400,  "LOCAL"),
    "Supervisor":     (700,  900,  "PERMANENT"),
    "ForeMan":        (800,  1000, "PERMANENT"),
    "Electrician":    (600,  800,  "LOCAL"),
    "Fitter":         (500,  650,  "LOCAL"),
    "Line Man":       (400,  550,  "LOCAL"),
    "Worker":         (350,  480,  "LOCAL"),
    "Semi Technician":(550,  700,  "PERMANENT"),
}

# ── Leave reasons pool ───────────────────────────────────────────────────────

LEAVE_REASONS = [
    "Personal work at home village",
    "Medical treatment for family member",
    "Marriage ceremony in family",
    "Fever and body ache",
    "Child school admission formalities",
    "Agricultural work at native place",
    "Religious ceremony at home",
    "Eye treatment at district hospital",
]


class Command(BaseCommand):
    help = "Populate Docker test DB: groups, users, 100 employees, advances, leaves"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 1: POPULATING TEST DATA ===\n"
        ))

        with transaction.atomic():
            self._create_groups()
            king_user, manager_user = self._create_users()
            self._create_leave_policies()
            employees = self._create_employees(manager_user)
            self._create_advances(employees)
            self._create_leaves(employees, manager_user)

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Step 1 complete. Run step2_mark_attendance next.\n"
        ))

    # ── GROUPS ───────────────────────────────────────────────────────────────

    def _create_groups(self):
        self.stdout.write("Creating groups...")
        for name in ["King", "Manager", "Worker"]:
            group, created = Group.objects.get_or_create(name=name)
            status = "created" if created else "already exists"
            self.stdout.write(f"  Group '{name}': {status}")

    # ── USERS ────────────────────────────────────────────────────────────────

    def _create_users(self):
        self.stdout.write("\nCreating King and Manager users...")

        # King / superuser
        if User.objects.filter(username="cwms_owner").exists():
            king_user = User.objects.get(username="cwms_owner")
            self.stdout.write("  King user 'cwms_owner': already exists")
        else:
            king_user = User.objects.create_superuser(
                username="cwms_owner",
                password="cwms@2026",
                email="owner@sakuntalam.com",
                first_name="Shubham",
                last_name="Singh",
            )
            king_group = Group.objects.get(name="King")
            king_user.groups.add(king_group)
            self.stdout.write("  King user 'cwms_owner': created (pass: cwms@2026)")

        # Manager
        if User.objects.filter(username="manager1").exists():
            manager_user = User.objects.get(username="manager1")
            self.stdout.write("  Manager user 'manager1': already exists")
        else:
            manager_user = User.objects.create_user(
                username="manager1",
                password="manager@2026",
                email="manager@sakuntalam.com",
                first_name="Vikram",
                last_name="Sharma",
            )
            manager_group = Group.objects.get(name="Manager")
            manager_user.groups.add(manager_group)
            self.stdout.write("  Manager user 'manager1': created (pass: manager@2026)")

        return king_user, manager_user

    # ── LEAVE POLICIES ───────────────────────────────────────────────────────

    def _create_leave_policies(self):
        self.stdout.write("\nCreating leave policies...")
        policies = [
            ("LOCAL",     15),
            ("PERMANENT", 30),
        ]
        for emp_type, days in policies:
            policy, created = LeavePolicy.objects.get_or_create(
                employment_type=emp_type,
                defaults={"annual_leave_days": days},
            )
            status = "created" if created else "already exists"
            self.stdout.write(f"  {emp_type}: {days} days/year — {status}")

    # ── EMPLOYEES ────────────────────────────────────────────────────────────

    def _create_employees(self, manager_user):
        self.stdout.write("\nCreating 100 employees...")

        # Build name pool — shuffle for randomness
        names = []
        for first in FIRST_NAMES[:100]:
            last = random.choice(LAST_NAMES)
            names.append(f"{first} {last}")
        random.shuffle(names)

        # Role distribution for 100 employees
        role_distribution = [
            ("Mason",           20),
            ("Laborer",         20),
            ("Helper",          15),
            ("Worker",          15),
            ("Electrician",     8),
            ("Fitter",          7),
            ("Line Man",        5),
            ("Supervisor",      5),
            ("ForeMan",         3),
            ("Semi Technician", 2),
        ]

        worker_group = Group.objects.get(name="Worker")
        employees_created = []
        counter = 0

        for role_name, count in role_distribution:
            try:
                role_obj = Role.objects.get(name=role_name)
            except Role.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ Role '{role_name}' not found, skipping")
                )
                continue

            wage_min, wage_max, emp_type = ROLE_CONFIG[role_name]

            for i in range(count):
                name = names[counter]
                counter += 1
                username = f"emp_{counter:03d}"
                phone = f"9{random.randint(100000000, 999999999)}"
                daily_wage = Decimal(str(random.randint(wage_min, wage_max)))
                join_date = date(
                    random.randint(2022, 2025),
                    random.randint(1, 12),
                    random.randint(1, 28),
                )

                # PF/ESIC only for PERMANENT
                pf_applicable   = (emp_type == "PERMANENT")
                esic_applicable = (emp_type == "PERMANENT")

                # Create auth user for this employee
                user = User.objects.create_user(
                    username=username,
                    password="worker@2026",
                    first_name=name.split()[0],
                    last_name=" ".join(name.split()[1:]),
                )
                user.groups.add(worker_group)

                emp = Employee.objects.create(
                    user=user,
                    name=name,
                    phone_number=phone,
                    role=role_obj,
                    daily_wage=daily_wage,
                    employment_type=emp_type,
                    pf_applicable=pf_applicable,
                    esic_applicable=esic_applicable,
                    join_date=join_date,
                    is_active=True,
                    working_location="Sakuntalam Site - Raigarh",
                )
                employees_created.append(emp)

        self.stdout.write(
            self.style.SUCCESS(f"  ✅ {len(employees_created)} employees created")
        )
        return employees_created

    # ── ADVANCES ─────────────────────────────────────────────────────────────

    def _create_advances(self, employees):
        self.stdout.write("\nIssuing advances to ~25 employees...")

        # Pick 25 random employees for advances
        advance_employees = random.sample(employees, min(25, len(employees)))

        advance_amounts = [
            Decimal("2000"), Decimal("3000"), Decimal("5000"),
            Decimal("7000"), Decimal("10000"), Decimal("15000"),
        ]

        count = 0
        for emp in advance_employees:
            amount = random.choice(advance_amounts)
            # Issue date: random day in April (previous month — valid for advances)
            issued_date = date(2026, 4, random.randint(1, 28))
            try:
                issue_advance(emp, amount, issued_date)
                count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ Advance failed for {emp.name}: {e}")
                )

        # Give 5 employees TWO advances (staggered — tests FIFO)
        double_advance_employees = random.sample(advance_employees, min(5, len(advance_employees)))
        for emp in double_advance_employees:
            amount = random.choice([Decimal("2000"), Decimal("3000")])
            issued_date = date(2026, 3, random.randint(1, 28))
            try:
                issue_advance(emp, amount, issued_date)
                count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ Second advance failed for {emp.name}: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"  ✅ {count} advance records created")
        )

    # ── LEAVES ───────────────────────────────────────────────────────────────

    def _create_leaves(self, employees, manager_user):
        """
        Assign leaves for May 1-5 (current month, not future — passes clean()).
        ~15 employees get leave.
        """
        self.stdout.write("\nAssigning leaves for May 1-5...")

        leave_employees = random.sample(employees, min(15, len(employees)))
        leave_types = ["EL", "CL", "SL"]

        count = 0
        for emp in leave_employees:
            leave_type = random.choice(leave_types)
            # 1-3 day leave windows within May 1-5
            start_day = random.randint(1, 3)
            end_day = start_day + random.randint(0, 2)
            end_day = min(end_day, 5)

            from_date  = date(2026, 5, start_day)
            to_date    = date(2026, 5, end_day)
            total_days = (to_date - from_date).days + 1
            reason     = random.choice(LEAVE_REASONS)

            try:
                assign_leave(
                    employee=emp,
                    leave_type=leave_type,
                    from_date=from_date,
                    to_date=to_date,
                    total_days=total_days,
                    reason=reason,
                    address_on_leave="Native village, Chhattisgarh",
                    application_date=date(2026, 4, 30),
                    approved_by=manager_user,
                    department="Construction Site",
                )
                count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ Leave failed for {emp.name}: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"  ✅ {count} leave records assigned (May 1-5)")
        )
