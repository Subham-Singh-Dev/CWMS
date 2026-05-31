<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f2027,25:1a2a3a,50:203a43,75:1e3a5f,100:2c5364&height=200&section=header&text=CWMS&fontSize=80&fontColor=ffffff&animation=fadeIn&fontAlignY=36&desc=Contractor%20Workforce%20Management%20System&descAlignY=60&descSize=20&descColor=94a3b8" width="100%"/>

</div>

<div align="center">

[![CI](https://github.com/Subham-Singh-Dev/cwms/actions/workflows/ci.yml/badge.svg)](https://github.com/Subham-Singh-Dev/cwms/actions)
[![Live](https://img.shields.io/badge/Live_App-00b37e?style=for-the-badge&logo=render&logoColor=white)](https://cwms-1fdo.onrender.com/portal/login/)
[![API Docs](https://img.shields.io/badge/Swagger_Docs-85EA2D?style=for-the-badge&logo=swagger&logoColor=black)](https://cwms-1fdo.onrender.com/api/docs/)
[![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django_5.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-64748b?style=for-the-badge)](LICENSE)

</div>

<div align="center">

**A production-grade Django monolith that automates daily-wage workforce management for construction contractors.**  
Built for and deployed at a real contractor company managing workers across multiple sites.

[🚀 Live App](https://cwms-1fdo.onrender.com/portal/login/) · [📖 API Docs](https://cwms-1fdo.onrender.com/api/docs/) · [🐛 Report Bug](https://github.com/Subham-Singh-Dev/cwms/issues)

</div>

---

## 📋 Table of Contents

- [The Problem It Solves](#-the-problem-it-solves)
- [Performance](#-performance)
- [Architecture](#-architecture)
- [Multi-Site Architecture](#-multi-site-architecture)
- [Key Engineering Decisions](#-key-engineering-decisions)
- [Tech Stack](#-tech-stack)
- [User Roles](#-user-roles)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Setup & Installation](#-setup--installation)
- [Admin Setup After Deployment](#-admin-setup-after-deployment)
- [API Reference](#-api-reference)
- [URL Endpoints](#-url-endpoints)
- [Test Management Commands](#-test-management-commands)
- [Deployment](#-deployment)
- [Future Enhancements](#-future-enhancements)

---

## 💡 The Problem It Solves

> Built for a real construction contractor running 150–200 daily-wage workers across multiple sites in Chhattisgarh.

| Before CWMS | After CWMS |
|---|---|
| 6–8 hours of manual payroll every month | Payroll processed in under 10 minutes |
| 5–10% advance leakage from manual tracking | Zero leakage — FIFO auto-deduction |
| Frequent wage disputes with workers | Workers trust printed, signed payslips |
| Zero financial visibility for the owner | Real-time liability and cash flow dashboard |
| Managers overwriting each other's attendance | Site-scoped attendance — zero cross-site conflict |
| No way to track multiple site operations | Unified dashboard — owner sees all sites at once |

---

## ⚡ Performance

<div align="center">

| Metric | Value |
|---|---|
| Dashboard API (Redis cached) | **2118ms → 26ms** (98.8% faster) |
| Test coverage | **64%** |
| Concurrent workers handled | **150–500+** |
| Sites supported | **Unlimited** (site field driven) |
| CI | Every push to `main` |

</div>

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Client Layer                               │
│           Django Templates + Vanilla JS  │  JWT REST API            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                       Django 5.2 Monolith                            │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │employees │  │attendance│  │ payroll  │  │ billing  │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ expenses │  │  portal  │  │   king   │  │analytics │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
│  ┌──────────┐  ┌──────────────────────────────────────┐             │
│  │  leaves  │  │  transaction.atomic() + select_for_update()  │     │
│  └──────────┘  └──────────────────────────────────────┘             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │                          │
           ┌───────────────▼────────┐   ┌────────────▼─────────────┐
           │  PostgreSQL (Render)   │   │  Redis (django-redis      │
           │  Primary data store    │   │  + DummyCache fallback)   │
           └────────────────────────┘   └──────────────────────────┘
```

---

## 🗺 Multi-Site Architecture

> Added to support contractors operating across multiple geographically separated sites, where each site has its own manager handling attendance independently.

### The Problem This Solves

When multiple managers mark attendance from different locations using a shared system, a naive implementation loads all employees for every manager. The first manager to submit overwrites the attendance for employees they've never seen, causing data corruption.

### How It Works

**`ManagerProfile`** — a new model in `portal/models.py` that links each manager `User` to their assigned site:

```python
class ManagerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    site = models.CharField(max_length=100, choices=SITE_CHOICES)
```

**`Employee.site`** — every employee is tagged with their work location:

```python
# employees/models.py
site = models.CharField(max_length=100, choices=SITE_CHOICES, default='raigarh')
```

**Scoped bulk attendance view** — the view reads `request.user.manager_profile.site` and filters the employee queryset before rendering. A manager physically cannot see or submit attendance for another site's employees:

```python
try:
    manager_site = request.user.manager_profile.site
except Exception:
    if request.user.is_superuser:
        manager_site = None   # King/superuser sees all employees
    else:
        messages.error(request, "No site assigned. Contact admin.")
        return redirect('manager_dashboard')

workers = Employee.objects.filter(is_active=True, site=manager_site)
```

### Site Layout (Production)

```
CWMS
 ├── Raigarh   →  manager_raigarh   →  70 employees
 ├── Bhilai    →  manager_bhilai    →  60 employees
 └── Korba     →  manager_korba     →  30 employees
                                       ─────────────
                                       160 employees total
```

### Rules

- Each manager sees **only their site's employees** in bulk attendance
- King (owner) sees **all employees** across all sites — no restriction
- Adding a new site requires one line in `SITE_CHOICES` — no code changes
- All other modules (payroll, advances, expenses, billing) are **not scoped** — any manager can operate them from any location

---

## ⚙️ Key Engineering Decisions

> These are the decisions that make CWMS production-safe — not just functional.

<details>
<summary><strong>🔒 FIFO Advance Deduction with <code>transaction.atomic()</code></strong></summary>

When payroll runs for 100–500+ workers concurrently, naive advance deduction causes race conditions — two payroll runs can read the same outstanding balance simultaneously and both deduct from it. CWMS uses `select_for_update()` inside `transaction.atomic()` to row-lock advance records per worker, ensuring FIFO recovery is deterministic with zero leakage.

```python
with transaction.atomic():
    advances = Advance.objects.select_for_update().filter(
        employee=employee, settled=False
    ).order_by('issued_date')   # FIFO — oldest debt recovered first
    # deduct from net salary until fully recovered or salary exhausted
```
</details>

<details>
<summary><strong>🗺 Site-Scoped Attendance with ManagerProfile</strong></summary>

Multi-location deployments need managers restricted to their own site's employees. CWMS introduced `ManagerProfile` (a `OneToOneField` to `User`) that stores each manager's assigned site. The bulk attendance view reads this profile on every request and filters the employee queryset accordingly.

Non-superusers without a `ManagerProfile` are **hard-blocked** with a clear error message and redirect — there is no silent fallback to all employees. This prevents accidental cross-site attendance writes.

King (superuser) accounts bypass the check and see all employees, enabling a consolidated view across sites.
</details>

<details>
<summary><strong>🛡 3-Role RBAC with IDOR Protection</strong></summary>

Three roles — `Manager`, `Worker`, `King` — each enforced by dedicated decorators and scoped queryset filters. A worker fetching `/payroll/payslip/<id>/` cannot access another worker's payslip; the view filters by `request.user` before returning any record.

- Manager login: username + password → `@manager_required`
- Worker login: phone number + password → `@worker_required`
- King login: dedicated secure URL + `king_authenticated` session flag → `@king_required`
</details>

<details>
<summary><strong>📸 Immutable Salary Snapshots</strong></summary>

Once a salary is generated and marked paid, its data is snapshotted — including the PF and ESIC rates used at time of generation. Future rate changes or attendance edits do not retroactively alter past salaries. Critical for financial auditability and compliance.
</details>

<details>
<summary><strong>⚡ Redis Caching with DummyCache Fallback</strong></summary>

CWMS uses `django-redis` for dashboard and API caching. If `REDIS_URL` is not set, it gracefully falls back to Django's `DummyCache` — no 500 errors on simpler deployments.

| Cache Key Pattern | TTL |
|---|---|
| `api:attendance:{user_id}:{YYYY-MM-DD}` | 5 min |
| `api:employees:{user_id}` | 5 min |
| `api:advances:{user_id}:{employee_id\|all}` | 1 hour |
| `activity:manager:{user_id}` | 5 min |
| `activity:king:{user_id}` | 5 min |
| `dashboard:manager:{user_id}:{YYYY-MM}:{session}` | 5 min |
| `dashboard:king:{user_id}:{YYYY-MM}:{session}` | 5 min |
| `employee:list:{user_id}:{session}:{query}` | 1 hour |
| `advance:register:{user_id}:{session}:{query}` | 1 hour |

Cache invalidation is centralized in `config/cache_utils.py` using batched SCAN+DEL. Write paths (create/update/delete) call this helper automatically.

**Cache bypass for Django messages:** The manager dashboard is cached as full HTML. If a pending Django message exists in the session (e.g. redirect from bulk attendance with no site assigned), the cache is skipped to ensure the message renders correctly:

```python
cached_html = cache.get(cache_key)
if cached_html and not messages.get_messages(request):
    return HttpResponse(cached_html)
```
</details>

<details>
<summary><strong>📅 Bulk Attendance — Past Date Integrity</strong></summary>

Two production-safety rules enforced in the bulk attendance view:

**Default Absent, not Present.** When a manager opens bulk attendance for a date with no existing records, employees default to `Absent` — not `Present`. This prevents ghost attendance from being silently committed when a manager doesn't explicitly mark every worker.

**GET summary from DB for past dates.** The attendance summary strip (present/absent/half-day/leave counts) is calculated from actual database records on GET requests — not just from the POST submission. Navigating to any past date shows the real attendance distribution without needing to save first.

```python
if request.method == "POST":
    summary_present = present   # in-memory count from just-saved data
else:
    existing = Attendance.objects.filter(date=selected_date, employee__in=workers)
    summary_present  = existing.filter(status='P').count()
    summary_absent   = existing.filter(status='A').count()
    summary_half_day = existing.filter(status='H').count()
    summary_leave    = existing.filter(status='L').count()
```
</details>

<details>
<summary><strong>🔐 7-Day Expense Edit Lock</strong></summary>

Expenses cannot be edited or deleted after 7 days — enforced at the view layer. This prevents retroactive accounting manipulation and protects monthly closure integrity.
</details>

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | Django 5.2 + Django REST Framework |
| Database | SQLite (dev) · PostgreSQL via `DATABASE_URL` (prod) |
| Auth | Session-based (portal) · JWT via `djangorestframework-simplejwt` (API) |
| API Docs | drf-spectacular (Swagger / OpenAPI 3.0) |
| Caching | django-redis with DummyCache fallback |
| PDF Generation | xhtml2pdf |
| Financial Arithmetic | Python `Decimal` — zero float errors |
| Transaction Safety | `transaction.atomic()` + `select_for_update()` |
| Frontend | Django Templates · Vanilla JS · CSS3 |
| Static Files | WhiteNoise |
| CI/CD | GitHub Actions → auto-deploy to Render on `main` |
| Deployment | Render (web service + managed PostgreSQL) |
| Testing | pytest + pytest-django · 64% coverage |

---

## 👥 User Roles

| Role | Group Name | Access | Login |
|---|---|---|---|
| **Manager** | `Manager` | Full operational control — scoped to their assigned site for attendance | Username + password |
| **Worker** | `Worker` | Read-only — own profile, attendance, payslips | Phone number + password |
| **King (Owner)** | `King` | Strategic + financial — full visibility across all sites | Secure URL |

> **Note:** Managers require a `ManagerProfile` with a `site` assignment to access bulk attendance. Accounts without a profile are blocked with a clear error message. King/superuser accounts bypass this check and see all sites.

---

## ✨ Features

<details>
<summary><strong>💰 Payroll Engine</strong></summary>

- Monthly salary generation from attendance records
- FIFO advance deduction with row locks inside `transaction.atomic()`
- PF and ESIC deductions with rates snapshotted per salary record
- Immutable salary snapshots after mark-paid
- Paid leave sourced from approved leave records (status `L`)
- Annual leave policy: Permanent 30 days, Local 15 days
- Overtime calculation by role
- CSV export for monthly registers
</details>

<details>
<summary><strong>📅 Attendance System</strong></summary>

- Daily tracking: Present / Half Day / Absent / Leave
- **Multi-site bulk attendance UI** — each manager sees only their site's employees, preventing cross-site overwrites
- Sticky summary strip showing Present / Half Day / Absent / Leave counts, visible while scrolling
- Past-date attendance loads real records from DB — not defaults
- Overtime hours per attendance record
- Validation: current-month only; future dates allowed only for approved leave; overtime only when status is Present
- Default status for new records is **Absent** (not Present) to prevent accidental ghost attendance
</details>

<details>
<summary><strong>💸 Advance Management</strong></summary>

- Issue cash loans to active employees
- Automatic FIFO recovery during payroll run
- Partial recovery tracking across multiple months
- Real-time outstanding balance display per worker
- Advance register with outstanding and settled filters
</details>

<details>
<summary><strong>🏖 Leave Management</strong></summary>

- Annual leave policy per employment type: Permanent 30 days, Local 15 days
- Leave types: Earned Leave (EL), Casual Leave (CL), Sick Leave (SL)
- Leave allocation and usage tracked per employee per year
- Assigning leave creates attendance rows with `L` status automatically
- Leave blocked if salary for that month is already paid
- Leave sanction letter PDF export via xhtml2pdf
</details>

<details>
<summary><strong>👷 Employee Management</strong></summary>

- Full employee master with statutory fields (PF number, ESIC, bank details, IDs)
- **Site field** — each employee tagged to a work location for manager scoping
- Employment type: `LOCAL` or `PERMANENT` (drives PF/ESIC applicability and leave quota)
- Auto-generated system usernames (`EMPxxxxx`) on creation
- Worker login via phone number + password
- Add / edit / deactivate employees
</details>

<details>
<summary><strong>🖥 Worker Portal (Enhanced Dashboard)</strong></summary>

- Unified worker dashboard: salary summary, attendance calendar, leave balance, advances, payslips
- Light/dark theme toggle with persistent preference
- Visual status chips, progress bars, and empty-state messaging
- Mobile-first, responsive layout for on-site usage
</details>

<details>
<summary><strong>📄 Billing Module</strong></summary>

- Upload vendor bills (PDF)
- GST calculated at 18%
- Partial payments supported; paid status derived from remaining balance
- Debtor and client bill types
- Billing PDF export
</details>

<details>
<summary><strong>📊 Daily Expenses</strong></summary>

- Categories: Food, Fuel, Travel, Material, Misc
- Payment modes: Cash, UPI, Bank
- Daily / Weekly / Monthly aggregates
- 7-day edit/delete lock (accounting safety)
- CSV and PDF export
</details>

<details>
<summary><strong>🧾 Audit Log</strong></summary>

- Full activity trail: who did what, when, from which IP
- Covers attendance, payroll, advances, expenses, bills, revenue, work orders
- Scope-aware: King sees all actions; Manager sees their own and worker actions
- CSV and PDF export for both roles
</details>

<details>
<summary><strong>👑 King (Owner) Dashboard</strong></summary>

- KPIs: payroll liability, expenses, revenue, cash flow, attendance — **aggregated across all sites**
- Work order lifecycle management
- Manual revenue register + ledger accounts + ledger entries
- Ledger PDF export with party filters
</details>

---

## 📁 Project Structure

```
CWMS/
├── manage.py
├── requirements.txt
├── Procfile                       # gunicorn for Render
├── build.sh / render_setup.sh     # migrate + collectstatic
├── .env.example
├── docker-compose.yml
├── populate_database.py           # demo data seeder
├── config/                        # settings, URLs, wsgi, cache_utils
├── analytics/                     # audit history + CSV/PDF exports
├── attendance/                    # daily tracking + bulk UI
├── billing/                       # vendor bill management
├── employees/                     # employee master + role + site field
├── expenses/                      # daily expenses + 7-day lock
├── king/                          # owner dashboard, work orders, ledger
├── leaves/                        # leave policy, allocation, PDF letters
├── payroll/                       # payroll engine + FIFO advances + payslips
├── portal/
│   ├── models.py                  # ManagerProfile (site assignment per manager)
│   ├── admin.py                   # ManagerProfile admin registration
│   ├── views.py                   # site-scoped bulk attendance + dashboards
│   └── templates/portal/
├── static/                        # CSS, JS, fonts (WhiteNoise served)
├── media/                         # uploaded bills and documents
└── .github/
    └── workflows/
        └── ci.yml
```

---

## 🚀 Setup & Installation

### Prerequisites

- Python 3.11+
- Redis 7+ (optional — falls back to DummyCache)
- pip

### Local Setup

```bash
# 1. Clone
git clone https://github.com/Subham-Singh-Dev/cwms.git
cd cwms

# 2. Virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Environment variables
cp .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL, REDIS_URL

# 5. Migrate
python manage.py migrate

# 6. Create superuser (becomes Owner/King)
python manage.py createsuperuser

# 7. (Optional) Seed demo data
python populate_database.py

# 8. Run
python manage.py runserver
```

### Docker

```bash
docker-compose up --build
# Update .env.docker for credentials before running
# Starts PostgreSQL, Redis, and the app (gunicorn)
```

### Environment Variables

```env
SECRET_KEY=replace-with-a-strong-secret-key
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
CSRF_TRUSTED_ORIGINS=http://localhost:8000
REDIS_URL=redis://127.0.0.1:6379/1

# Optional — used in PDF exports
BRAND_COMPANY_NAME=Your Company Name
BRAND_ACCOUNT_NAME=YOUR COMPANY NAME
BRAND_COMPANY_ADDRESS=
BRAND_COMPANY_GSTIN=
```

---

## 🔧 Admin Setup After Deployment

After running migrations and creating users, complete these one-time steps in Django admin (`/admin/`) before handing the system to managers.

### Step 1 — Assign Sites to Managers

Navigate to **Admin → Portal → Manager Profiles** and create one profile per manager user:

| Manager Username | Site |
|---|---|
| `manager_raigarh` | `raigarh` |
| `manager_bhilai` | `bhilai` |
| `manager_korba` | `korba` |

> Without a `ManagerProfile`, a manager will be redirected with an error when they try to access bulk attendance.

### Step 2 — Tag Employees to Sites

Navigate to **Admin → Employees** and set the `site` field for each employee. Alternatively, use the bulk-edit action in the employee list view.

### Step 3 — Verify

Log in as each manager and open Mark Attendance. Each manager should see only their site's employees. Log in as King and confirm the owner dashboard aggregates all sites.

---

## 📖 API Reference

Full interactive docs: **https://cwms-1fdo.onrender.com/api/docs/**

### Auth Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/token/` | Obtain JWT access + refresh token |
| POST | `/api/token/refresh/` | Refresh expired access token |

Access token: 5 minutes. Refresh token: 24 hours. All endpoints require `Authorization: Bearer <token>`.

### Resources

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/api/employees/` | Manager | List active employees |
| GET/PUT/DELETE | `/api/employees/<id>/` | Authenticated | Employee detail |
| GET/POST | `/api/attendance/` | Manager | Attendance records |
| GET | `/api/payroll/?month=YYYY-MM` | Manager | Salary list |
| GET/POST | `/api/advances/` | Manager | Advances list / issue |
| GET | `/api/activity/` | Manager | Recent audit feed (cached) |

> **Security note:** Employee detail endpoints currently check authentication but do not enforce manager-only access. Lock these down before exposing to untrusted clients.

### Quick Start

```bash
# Get token
curl -X POST https://cwms-1fdo.onrender.com/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_user", "password": "your_pass"}'

# Use token
curl https://cwms-1fdo.onrender.com/api/employees/ \
  -H "Authorization: Bearer <access_token>"
```

---

## 🔗 URL Endpoints

<details>
<summary><strong>Authentication</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET/POST | `/portal/login/` | Worker / Manager login |
| GET | `/portal/logout/` | Portal logout |
| GET/POST | `/king/secure/owner-x7k2/` | King secure login |
| GET | `/king/logout/` | King logout |
</details>

<details>
<summary><strong>Manager — Attendance & Payroll</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/portal/manager/dashboard/` | Manager dashboard |
| GET/POST | `/portal/manager/attendance/bulk/` | Bulk attendance (site-scoped) |
| POST | `/portal/manager/run-payroll/` | Trigger payroll batch |
| GET/POST | `/portal/manager/advances/issue/` | Issue advance |
| GET/POST | `/portal/manager/advances/register/` | Advance register |
| GET | `/payroll/summary/` | Payroll batch summary |
| GET | `/payroll/manager/payroll/salaries/` | Salary list |
| POST | `/payroll/manager/payroll/salaries/generate/` | Generate one salary |
| POST | `/payroll/manager/payroll/salaries/mark-paid/` | Mark salary paid |
| GET | `/payroll/manager/payroll/salaries/export/` | CSV export |
| GET | `/payroll/payslip/<salary_id>/` | Download payslip (role-scoped) |
</details>

<details>
<summary><strong>Employees, Billing & Expenses</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/manager/employees/` | Employee list |
| GET/POST | `/manager/employees/add/` | Add employee |
| GET | `/manager/employees/profile/<id>/` | Employee profile |
| GET/POST | `/manager/billing/` | Billing dashboard / upload |
| POST | `/toggle_bill_status/<bill_id>/` | Toggle paid/unpaid |
| POST | `/record-payment/<bill_id>/` | Record partial payment |
| GET | `/manager/billing/pdf/` | Billing PDF |
| GET/POST | `/manager/expenses/` | Expenses / add |
| GET/POST | `/manager/expenses/edit/<id>/` | Edit (7-day lock enforced) |
| GET | `/manager/expenses/export/` | CSV |
| GET | `/manager/expenses/pdf/` | PDF |
</details>

<details>
<summary><strong>Leaves</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET/POST | `/leaves/assign/` | Assign leave |
| GET | `/leaves/list/` | Leave list |
| GET | `/leaves/pdf/<leave_id>/` | Sanction letter PDF |
</details>

<details>
<summary><strong>Worker Portal</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/portal/dashboard/` | Worker home |
| GET | `/portal/profile/` | Worker profile |
| GET | `/portal/download-payslip/<salary_id>/` | Download payslip |
</details>

<details>
<summary><strong>King (Owner) & Audit</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/king/dashboard/` | Business analytics (all sites) |
| GET | `/king/workorders/` | Work orders |
| GET | `/king/revenue/` | Revenue dashboard |
| GET | `/king/ledger/` | Ledger view |
| GET | `/king/ledger/pdf/` | Ledger PDF |
| GET | `/king/accounts/` | Account list |
| GET | `/king/audit/` | Full audit history |
| GET | `/king/audit/export/csv/` | Audit CSV |
| GET | `/king/audit/export/pdf/` | Audit PDF |
| GET | `/portal/manager/audit/` | Manager audit history (scoped) |
</details>

---

## 🧪 Test Management Commands

CWMS ships with a 4-step management command suite for full end-to-end testing on a clean database (designed for Docker).

```bash
# Run in order on a fresh DB
docker-compose exec web python manage.py step1_populate_data
docker-compose exec web python manage.py step2_mark_attendance
docker-compose exec web python manage.py step3_generate_payroll
docker-compose exec web python manage.py step4_verify_payroll
```

| Command | What It Does |
|---|---|
| `step1_populate_data` | Creates groups, roles, King user, 3 site managers with `ManagerProfile`, 160 employees across Raigarh/Bhilai/Korba, ~35 advances, ~20 leaves |
| `step2_mark_attendance` | Marks attendance for all 160 employees for the full month using `bulk_create(ignore_conflicts=True)` — preserves existing leave records |
| `step3_generate_payroll` | Calls `generate_monthly_salary()` for every active employee, prints gross/advance/net per employee |
| `step4_verify_payroll` | Full math audit: net = gross − deductions, deduction breakdown, PF/ESIC checks, negative pay check, attendance cross-check — prints verdict |

### Test Credentials (after step1)

| Role | Username | Password | Login URL |
|---|---|---|---|
| King | `cwms_owner` | `cwms@2026` | `/king/secure/owner-x7k2/` |
| Manager (Raigarh) | `manager_raigarh` | `raigarh@2026` | `/portal/login/` |
| Manager (Bhilai) | `manager_bhilai` | `bhilai@2026` | `/portal/login/` |
| Manager (Korba) | `manager_korba` | `korba@2026` | `/portal/login/` |
| Workers | `emp_001` → `emp_160` | `worker@2026` | `/portal/login/` (phone + pass) |

---

## 🚢 Deployment

### CI/CD (GitHub Actions)

```
push to main
  → pip install -r requirements.txt
  → python manage.py check
  → python manage.py test
  → auto-deploy to Render
```

### Production (Self-Hosted)

```
OS:        Ubuntu 22.04 LTS
Web:       Nginx + Gunicorn
Database:  PostgreSQL 14+
Cache:     Redis 7+
Process:   Systemd
SSL:       Let's Encrypt
RAM:       2GB minimum
```

### Production Checklist

- [ ] `DEBUG=False` and a strong `SECRET_KEY` in environment
- [ ] `REDIS_URL` set with correct DB index; verify `CACHES` in `settings.py` matches
- [ ] Route `cwms.cache` logger to Sentry or file for Redis failure alerts
- [ ] Set Redis `maxmemory` and eviction policy for your cache footprint
- [ ] Create `ManagerProfile` for every manager user via Django admin
- [ ] Tag all employees with their `site` value before go-live
- [ ] Verify each manager can only see their site's employees in bulk attendance
- [ ] Lock down `/api/employees/<id>/` to manager-only access
- [ ] Configure AWS S3 or Cloudflare R2 for media file storage

---

## 🔮 Future Enhancements

- [ ] Multi-tenant support (one instance, multiple contractor clients)
- [ ] SMS notifications for payslip delivery
- [ ] Biometric attendance integration
- [ ] Mobile app (React Native)
- [ ] Budget tracking and forecasting
- [ ] Tax and compliance automation
- [ ] Site-level financial breakdown in owner dashboard

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2c5364,50:203a43,100:0f2027&height=120&section=footer" width="100%"/>

*Built to solve real problems for real contractors — not a demo project.*

</div>