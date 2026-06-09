"""
Management Command: step1_populate_data
=======================================
Creates:
  - Groups     : King, Manager, Worker
  - Sites      : Raigarh (70 emp), Bhilai (60 emp), Korba (30 emp)
  - Users      : 1 King (superuser) + 3 Managers (one per site)
  - Profiles   : ManagerProfile for each manager (site-scoped)
  - Employees  : 160 total across 3 sites
  - Advances   : ~35 employees
  - Leaves     : ~20 employees (May 1-5)
  - Policies   : LeavePolicy for LOCAL and PERMANENT

Architecture note:
  ManagerProfile links each manager User to their site.
  bulk_attendance view uses manager_profile.site to scope employee list.
  Cross-site attendance writes are blocked at the view layer.

Run:
    docker-compose exec web python manage.py step1_populate_data
"""

import random
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from employees.models import Employee, Role
from leaves.models import LeavePolicy
from leaves.services import assign_leave
from payroll.services import issue_advance
from portal.models import ManagerProfile


# ── Real Indian names pool (160+) ────────────────────────────────────────────

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
    "Hemant", "Shyam", "Gopal", "Brij", "Trilokesh", "Chandresh",
    "Ramavtar", "Kalyan", "Durgesh", "Arvind", "Praveen", "Naveen",
    "Jitendra", "Surendra", "Dhirendra", "Virendra", "Narendra", "Yogendra",
    "Rajendra", "Mahendra", "Devendra", "Upendra", "Bhupendra", "Gajendra",
    "Sailendra", "Rajiv", "Sanjeev", "Harshit", "Yashpal",
    "Baldev", "Jagdev", "Surjit", "Avtar", "Darshan", "Roshan",
    "Bhagwan", "Ishwar", "Shiv", "Ram", "Hari", "Kripa", "Madan",
    "Chandan", "Nandan", "Brijnandan", "Ramanandan", "Krishnanand",
    "Tejpal", "Dalip", "Satpal", "Rajpal", "Harpal", "Amrit",
    "Sukhwant", "Kulwant", "Jaswant", "Balwant", "Dilbag", "Harbag",
]

LAST_NAMES = [
    "Kumar", "Singh", "Verma", "Sharma", "Yadav", "Gupta", "Mishra",
    "Tiwari", "Pandey", "Joshi", "Patel", "Shah", "Mehta", "Jain",
    "Agarwal", "Bansal", "Goel", "Mittal", "Saxena", "Srivastava",
    "Chauhan", "Rathore", "Rajput", "Solanki", "Parmar", "Bhatt",
    "Nair", "Pillai", "Menon", "Krishnan", "Iyer", "Rao", "Reddy",
    "Naidu", "Choudhary", "Dubey", "Tripathi", "Shukla", "Upadhyay",
    "Kesarwani", "Soni", "Lal", "Das", "Sahu", "Dewangan", "Netam",
]

# ── Role config: (wage_min, wage_max, employment_type) ──────────────────────

ROLE_CONFIG = {
    "Mason":           (500,  650,  "LOCAL"),
    "Laborer":         (350,  450,  "LOCAL"),
    "Helper":          (300,  400,  "LOCAL"),
    "Supervisor":      (700,  900,  "PERMANENT"),
    "ForeMan":         (800, 1000,  "PERMANENT"),
    "Electrician":     (600,  800,  "LOCAL"),
    "Fitter":          (500,  650,  "LOCAL"),
    "Line Man":        (400,  550,  "LOCAL"),
    "Worker":          (350,  480,  "LOCAL"),
    "Semi Technician": (550,  700,  "PERMANENT"),
}

# ── Site configuration ───────────────────────────────────────────────────────

SITE_CONFIG = [
    {
        "key":              "raigarh",
        "label":            "Raigarh",
        "emp_count":        70,
        "manager_username": "manager_raigarh",
        "manager_pass":     "raigarh@2026",
        "manager_first":    "Vikram",
        "manager_last":     "Sharma",
    },
    {
        "key":              "bhilai",
        "label":            "Bhilai",
        "emp_count":        60,
        "manager_username": "manager_bhilai",
        "manager_pass":     "bhilai@2026",
        "manager_first":    "Arun",
        "manager_last":     "Verma",
    },
    {
        "key":              "korba",
        "label":            "Korba",
        "emp_count":        30,
        "manager_username": "manager_korba",
        "manager_pass":     "korba@2026",
        "manager_first":    "Sunil",
        "manager_last":     "Tiwari",
    },
]

# Role distribution percentages (applied to each site's headcount)
ROLE_DISTRIBUTION = [
    ("Mason",           0.18),
    ("Laborer",         0.18),
    ("Helper",          0.12),
    ("Worker",          0.15),
    ("Electrician",     0.08),
    ("Fitter",          0.08),
    ("Line Man",        0.05),
    ("Supervisor",      0.07),
    ("ForeMan",         0.05),
    ("Semi Technician", 0.04),
]

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
    help = "Populate test DB: 3 sites, 3 managers, 160 employees, advances, leaves"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== STEP 1: POPULATING TEST DATA (MULTI-SITE) ===\n"
        ))

        with transaction.atomic():
            self._create_groups()
            self._create_roles()
            king_user = self._create_king()
            managers  = self._create_managers()
            self._create_leave_policies()
            all_employees = self._create_employees()
            self._create_advances(all_employees)
            self._create_leaves(all_employees, managers)

        self._print_credentials(king_user, managers)

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Step 1 complete. Run step2_mark_attendance next.\n"
        ))

    # ── GROUPS ───────────────────────────────────────────────────────────────

    def _create_groups(self):
        self.stdout.write("Creating groups...")
        for name in ["King", "Manager", "Worker"]:
            group, created = Group.objects.get_or_create(name=name)
            self.stdout.write(
                f"  Group '{name}': {'created' if created else 'already exists'}"
            )

    # ── ROLES ────────────────────────────────────────────────────────────────

    def _create_roles(self):
        self.stdout.write("\nCreating roles...")
        for role_name in ROLE_CONFIG:
            role, created = Role.objects.get_or_create(
                name=role_name,
                defaults={"overtime_rate_per_hour": Decimal("50.00")},
            )
            self.stdout.write(
                f"  Role '{role_name}': {'created' if created else 'already exists'}"
            )

    # ── KING ─────────────────────────────────────────────────────────────────

    def _create_king(self):
        self.stdout.write("\nCreating King (owner) user...")
        if User.objects.filter(username="cwms_owner").exists():
            user = User.objects.get(username="cwms_owner")
            self.stdout.write("  King 'cwms_owner': already exists")
            return user

        user = User.objects.create_superuser(
            username="cwms_owner",
            password="cwms@2026",
            email="owner@cwms.com",
            first_name="Shubham",
            last_name="Singh",
        )
        user.groups.add(Group.objects.get(name="King"))
        self.stdout.write("  King 'cwms_owner': created")
        return user

    # ── MANAGERS ─────────────────────────────────────────────────────────────

    def _create_managers(self):
        """Create one manager per site and assign ManagerProfile."""
        self.stdout.write("\nCreating managers (one per site)...")
        manager_group = Group.objects.get(name="Manager")
        managers = {}

        for site in SITE_CONFIG:
            uname = site["manager_username"]

            if User.objects.filter(username=uname).exists():
                user = User.objects.get(username=uname)
                self.stdout.write(f"  Manager '{uname}': already exists")
            else:
                user = User.objects.create_user(
                    username=uname,
                    password=site["manager_pass"],
                    first_name=site["manager_first"],
                    last_name=site["manager_last"],
                )
                user.groups.add(manager_group)
                self.stdout.write(
                    f"  Manager '{uname}' ({site['label']}): created"
                )

            # Create or update ManagerProfile
            profile, p_created = ManagerProfile.objects.get_or_create(
                user=user,
                defaults={"site": site["key"]},
            )
            if not p_created and profile.site != site["key"]:
                profile.site = site["key"]
                profile.save()

            self.stdout.write(
                f"    ↳ ManagerProfile site = '{site['key']}' "
                f"({'created' if p_created else 'updated'})"
            )
            managers[site["key"]] = user

        return managers

    # ── LEAVE POLICIES ───────────────────────────────────────────────────────

    def _create_leave_policies(self):
        self.stdout.write("\nCreating leave policies...")
        for emp_type, days in [("LOCAL", 15), ("PERMANENT", 30)]:
            policy, created = LeavePolicy.objects.get_or_create(
                employment_type=emp_type,
                defaults={"annual_leave_days": days},
            )
            self.stdout.write(
                f"  {emp_type}: {days} days/year — "
                f"{'created' if created else 'already exists'}"
            )

    # ── EMPLOYEES ────────────────────────────────────────────────────────────

    def _create_employees(self):
        """
        Create employees distributed across sites.
        Each employee is tagged with their site field.
        """
        self.stdout.write("\nCreating employees across 3 sites...")

        # Build unique name pool
        names = list({
            f"{fn} {random.choice(LAST_NAMES)}" for fn in FIRST_NAMES
        })
        random.shuffle(names)
        name_iter = iter(names)

        worker_group = Group.objects.get(name="Worker")
        all_employees = []
        username_counter = 1

        for site in SITE_CONFIG:
            site_key   = site["key"]
            site_label = site["label"]
            emp_count  = site["emp_count"]

            self.stdout.write(
                f"\n  Site: {site_label} — creating {emp_count} employees"
            )

            # Build role slot list for this site
            role_slots = []
            remaining = emp_count
            for idx, (role_name, pct) in enumerate(ROLE_DISTRIBUTION):
                if idx == len(ROLE_DISTRIBUTION) - 1:
                    count = remaining  # absorb rounding remainder
                else:
                    count = max(1, round(emp_count * pct))
                    remaining -= count
                role_slots.extend([role_name] * count)

            random.shuffle(role_slots)

            site_employees = []
            for role_name in role_slots:
                try:
                    name = next(name_iter)
                except StopIteration:
                    name = f"Worker {username_counter}"

                wage_min, wage_max, emp_type = ROLE_CONFIG[role_name]
                role_obj = Role.objects.get(name=role_name)

                phone = f"9{random.randint(100000000, 999999999)}"
                while Employee.objects.filter(phone_number=phone).exists():
                    phone = f"9{random.randint(100000000, 999999999)}"

                daily_wage = Decimal(str(random.randint(wage_min, wage_max)))
                join_date  = date(
                    random.randint(2022, 2025),
                    random.randint(1, 12),
                    random.randint(1, 28),
                )

                pf_applicable   = (emp_type == "PERMANENT")
                esic_applicable = (emp_type == "PERMANENT")

                username = f"emp_{username_counter:03d}"
                username_counter += 1

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
                    site=site_key,
                    working_location=f"CWMS Site - {site_label}",
                )
                site_employees.append(emp)

            self.stdout.write(
                self.style.SUCCESS(
                    f"    ✅ {len(site_employees)} employees created for {site_label}"
                )
            )
            all_employees.extend(site_employees)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✅ Total employees created: {len(all_employees)}"
            )
        )
        return all_employees

    # ── ADVANCES ─────────────────────────────────────────────────────────────

    def _create_advances(self, employees):
        """Issue advances to ~35 employees; 8 get two advances (FIFO test)."""
        self.stdout.write("\nIssuing advances...")
        AMOUNTS = [
            Decimal("2000"), Decimal("3000"), Decimal("5000"),
            Decimal("7000"), Decimal("10000"), Decimal("15000"),
        ]

        targets = random.sample(employees, min(35, len(employees)))
        count = 0

        for emp in targets:
            amount      = random.choice(AMOUNTS)
            issued_date = date(2026, 4, random.randint(1, 28))
            try:
                issue_advance(emp, amount, issued_date)
                count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ Advance failed ({emp.name}): {e}")
                )

        # 8 employees get a second (older) advance — tests FIFO recovery
        double_targets = random.sample(targets, min(8, len(targets)))
        for emp in double_targets:
            amount      = random.choice([Decimal("2000"), Decimal("3000")])
            issued_date = date(2026, 3, random.randint(1, 28))
            try:
                issue_advance(emp, amount, issued_date)
                count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ 2nd advance failed ({emp.name}): {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"  ✅ {count} advance records created")
        )

    # ── LEAVES ───────────────────────────────────────────────────────────────

    # ── LEAVES ───────────────────────────────────────────────────────────────
    def _create_leaves(self, employees, managers):
        """Assign leaves for the first 5 days of the CURRENT month."""
        self.stdout.write("\nAssigning leaves (First 5 days of current month)...")
        LEAVE_TYPES = ["EL", "CL", "SL"]
        
        # Dynamic date calculation
        now = timezone.now()
        first_day = now.replace(day=1)
        
        targets = random.sample(employees, min(20, len(employees)))
        count = 0

        for emp in targets:
            manager_user = managers.get(emp.site, next(iter(managers.values())))
            leave_type = random.choice(LEAVE_TYPES)
            
            # Use dynamic dates relative to 'now'
            start_day = random.randint(1, 3)
            end_day = min(start_day + random.randint(0, 2), 5)
            total_days = (end_day - start_day) + 1

            try:
                assign_leave(
                    employee=emp,
                    leave_type=leave_type,
                    from_date=first_day.replace(day=start_day).date(),
                    to_date=first_day.replace(day=end_day).date(),
                    total_days=total_days,
                    reason=random.choice(LEAVE_REASONS),
                    address_on_leave="Native village, Chhattisgarh",
                    application_date=first_day.replace(day=1).date(), # Application start of month
                    approved_by=manager_user,
                    department="Construction Site",
                )
                count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f" ⚠ Leave failed ({emp.name}): {e}"))

        self.stdout.write(self.style.SUCCESS(f" ✅ {count} leave records assigned"))

    # ── CREDENTIALS SUMMARY ──────────────────────────────────────────────────

    def _print_credentials(self, king_user, managers):
        self.stdout.write("\n" + "═" * 60)
        self.stdout.write("  CREDENTIALS SUMMARY")
        self.stdout.write("═" * 60)

        self.stdout.write("\n  KING (Owner)")
        self.stdout.write(f"    Username : cwms_owner")
        self.stdout.write(f"    Password : cwms@2026")
        self.stdout.write(f"    Login    : /king/secure/owner-x7k2/")

        self.stdout.write("\n  MANAGERS")
        for site in SITE_CONFIG:
            self.stdout.write(
                f"    [{site['label']:8}] "
                f"Username: {site['manager_username']:<20} "
                f"Password: {site['manager_pass']}"
            )
            self.stdout.write(
                f"             Site key: {site['key']}  "
                f"Employees: {site['emp_count']}"
            )

        self.stdout.write("\n  WORKERS")
        self.stdout.write(f"    Username : emp_001 → emp_160")
        self.stdout.write(f"    Password : worker@2026")
        self.stdout.write(f"    Login    : /portal/login/ (phone + password)")

        self.stdout.write("\n  EMPLOYEE DISTRIBUTION")
        for site in SITE_CONFIG:
            count = Employee.objects.filter(site=site["key"]).count()
            self.stdout.write(
                f"    {site['label']:10}: {count} employees"
            )

        total = Employee.objects.filter(is_active=True).count()
        self.stdout.write(f"    {'TOTAL':10}: {total} employees")
        self.stdout.write("═" * 60 + "\n")