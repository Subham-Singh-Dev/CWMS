<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f2027,50:203a43,100:2c5364&height=180&section=header&text=CWMS&fontSize=72&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Contractor%20Workforce%20Management%20System&descAlignY=62&descSize=18&descColor=94a3b8" width="100%"/>

</div>

<div align="center">

[![CI](https://github.com/Subham-Singh-Dev/cwms/actions/workflows/ci.yml/badge.svg)](https://github.com/Subham-Singh-Dev/cwms/actions)
[![Live](https://img.shields.io/badge/Live_App-00b37e?style=for-the-badge&logo=render&logoColor=white)](https://cwms-1fdo.onrender.com/portal/login/)
[![API Docs](https://img.shields.io/badge/Swagger_Docs-85EA2D?style=for-the-badge&logo=swagger&logoColor=black)](https://cwms-1fdo.onrender.com/api/docs/)
[![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django_5.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-MIT-64748b?style=for-the-badge)](LICENSE)

**A production-grade Django backend that automates daily-wage workforce management for construction contractors.**
Live system managing 100-500+ workers for a real client.

[Live App](https://cwms-1fdo.onrender.com/portal/login/) · [API Docs](https://cwms-1fdo.onrender.com/api/docs/) · [Report Bug](https://github.com/Subham-Singh-Dev/cwms/issues)

</div>

---

## The Problem It Solves

| Before CWMS | After CWMS |
|---|---|
| 6-8 hours of manual payroll every month | Payroll processed in under 10 minutes |
| 5-10% advance leakage from manual tracking | Zero leakage - FIFO auto-deduction |
| Frequent wage disputes with workers | Workers trust printed, signed payslips |
| Zero financial visibility for the owner | Real-time liability and cash flow dashboard |

---

## Performance

<div align="center">

| Metric | Value |
|---|---|
| Dashboard API (Redis cached) | **2118ms -> 26ms** (98.8% faster) |
| Test coverage | **64%** |
| Concurrent workers handled | **100-500+** |
| CI | Every push to `main` |

</div>

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         Client Layer                          │
│          Django Templates + Vanilla JS  │  JWT REST API      │
└─────────────────────────┬────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                     Django 5.2 Monolith                       │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐    │
│  │employees │  │attendance│  │ payroll  │  │  billing  │    │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐    │
│  │ expenses │  │  portal  │  │   king   │  │ analytics │    │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘    │
│  ┌──────────┐                                                 │
│  │  leaves  │   transaction.atomic() + select_for_update()   │
│  └──────────┘                                                 │
└─────────────────────────┬────────────────────────────────────┘
                          │                        │
          ┌───────────────▼───────┐   ┌────────────▼────────┐
          │  PostgreSQL (Render)  │   │  Redis (django-redis │
          │  Primary data store   │   │  + DummyCache fallbk)│
          └───────────────────────┘   └─────────────────────┘
```

---

## Key Engineering Decisions

> These are the decisions that make CWMS production-safe - not just functional.

<details>
<summary><strong>FIFO Advance Deduction with <code>transaction.atomic()</code></strong></summary>

When payroll runs for 100-500+ workers concurrently, naive advance deduction causes race conditions - two payroll runs can read the same outstanding balance simultaneously and both deduct from it. CWMS uses `select_for_update()` inside `transaction.atomic()` to row-lock advance records per worker, ensuring FIFO recovery is deterministic with zero leakage.

```python
with transaction.atomic():
    advances = Advance.objects.select_for_update().filter(
        employee=employee, settled=False
    ).order_by('issued_date')   # FIFO - oldest debt first
    # deduct from net salary until fully recovered or salary exhausted
```
</details>

<details>
<summary><strong>3-Role RBAC with IDOR Protection</strong></summary>

Three roles - `Manager`, `Worker`, `King` - each enforced by dedicated decorators and scoped queryset filters. A worker fetching `/payroll/payslip/<id>/` cannot access another worker's payslip; the view filters by `request.user` before returning any record.

- Manager login: username + password -> `@manager_required`
- Worker login: phone number + password -> `@worker_required`
- King login: dedicated secure URL + `king_authenticated` session flag -> `@king_required`
</details>

<details>
<summary><strong>Immutable Salary Snapshots</strong></summary>

Once a salary is generated and marked paid, its data is snapshotted - including the PF and ESIC rates used at time of generation. Future rate changes or attendance edits do not retroactively alter past salaries. Critical for financial auditability and compliance.
</details>

<details>
<summary><strong>Redis Caching with DummyCache Fallback</strong></summary>

CWMS uses `django-redis` for dashboard and API caching. If `REDIS_URL` is not set, it gracefully falls back to Django's `DummyCache` - no 500 errors on simpler deployments.

| Cache Key Pattern | TTL |
|---|---|
| `api:attendance:{user_id}:{YYYY-MM-DD}` | 5 min |
| `api:employees:{user_id}` | 5 min |
| `api:advances:{user_id}:{employee_id|all}` | 1 hour |
| `activity:manager:{user_id}` | 5 min |
| `activity:king:{user_id}` | 5 min |
| `dashboard:manager:{user_id}:{YYYY-MM}:{session}` | 5 min |
| `dashboard:king:{user_id}:{YYYY-MM}:{session}` | 5 min |
| `employee:list:{user_id}:{session}:{query}` | 1 hour |
| `advance:register:{user_id}:{session}:{query}` | 1 hour |

Cache invalidation is centralized in `config/cache_utils.py` using batched SCAN+DEL. Write paths (create/update/delete) call this helper automatically.
</details>

<details>
<summary><strong>7-Day Expense Edit Lock</strong></summary>

Expenses cannot be edited or deleted after 7 days - enforced at the view layer. This prevents retroactive accounting manipulation and protects monthly closure integrity.
</details>

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | Django 5.2 + Django REST Framework |
| Database | SQLite (dev) · PostgreSQL via `DATABASE_URL` (prod) |
| Auth | Session-based (portal) · JWT via `djangorestframework-simplejwt` (API) |
| API Docs | drf-spectacular (Swagger / OpenAPI 3.0) |
| Caching | django-redis with DummyCache fallback |
| PDF Generation | xhtml2pdf |
| Financial Arithmetic | Python `Decimal` - zero float errors |
| Transaction Safety | `transaction.atomic()` + `select_for_update()` |
| Frontend | Django Templates · Vanilla JS · CSS3 |
| Static Files | WhiteNoise |
| CI/CD | GitHub Actions -> auto-deploy to Render on `main` |
| Deployment | Render (web service + managed PostgreSQL) |
| Testing | pytest + pytest-django · 64% coverage |

---

## User Roles

| Role | Group Name | Access | Login |
|---|---|---|---|
| **Manager** | `Manager` | Full operational control | Username + password |
| **Worker** | `Worker` | Read-only (own profile, attendance, payslips) | Phone + password |
| **King (Owner)** | `King` | Strategic + financial | Secure URL |

---

## Features

<details>
<summary><strong>Payroll Engine</strong></summary>

- Monthly salary generation from attendance records
- FIFO advance deduction with row locks inside `transaction.atomic()`
- PF and ESIC deductions with rates snapshotted per salary record
- Immutable salary snapshots after mark-paid
- Paid leave comes from approved leave records (status L)
- Annual leave policy: Permanent 30 days, Local 15 days
- Overtime calculation by role
- CSV export for monthly registers
</details>

<details>
<summary><strong>Attendance System</strong></summary>

- Daily tracking: Present / Half Day / Absent / Leave
- Bulk attendance UI - spreadsheet-style for 100+ workers in one page
- Overtime hours per attendance record
- Validation: current-month only; future dates allowed only for approved leave; overtime only when status is Present
</details>

<details>
<summary><strong>Advance Management</strong></summary>

- Issue cash loans to active employees
- Automatic FIFO recovery during payroll run
- Partial recovery tracking across multiple months
- Real-time outstanding balance display per worker
- Advance register with outstanding and settled filters
</details>

<details>
<summary><strong>Leave Management</strong></summary>

- Annual leave policy per employment type: Permanent 30 days, Local 15 days
- Leave types: Earned Leave (EL), Casual Leave (CL), Sick Leave (SL)
- Leave allocation and usage tracked per employee per year
- Assigning leave creates attendance rows with `L` status automatically
- Leave blocked if salary for that month is already paid
- Leave sanction letter PDF export via xhtml2pdf
</details>

<details>
<summary><strong>Employee Management</strong></summary>

- Full employee master with statutory fields (PF number, ESIC, bank details, IDs)
- Auto-generated system usernames (`EMPxxxxx`) on creation
- Worker login via phone number + password
- Add / edit / deactivate employees
</details>

<details>
<summary><strong>Billing Module</strong></summary>

- Upload vendor bills (PDF)
- GST calculated at 18%
- Partial payments supported; paid status derived from remaining balance
- Debtor and client bill types
- Billing PDF export
</details>

<details>
<summary><strong>Daily Expenses</strong></summary>

- Categories: Food, Fuel, Travel, Material, Misc
- Payment modes: Cash, UPI, Bank
- Daily / Weekly / Monthly aggregates
- 7-day edit/delete lock (accounting safety)
- CSV and PDF export
</details>

<details>
<summary><strong>Audit Log</strong></summary>

- Full activity trail: who did what, when, from which IP
- Covers attendance, payroll, advances, expenses, bills, revenue, work orders
- Scope-aware: King sees all actions; Manager sees their own and worker actions
- CSV and PDF export for both roles
</details>

<details>
<summary><strong>King (Owner) Dashboard</strong></summary>

- KPIs: payroll liability, expenses, revenue, cash flow, attendance
- Work order lifecycle management
- Manual revenue register + ledger accounts + ledger entries
- Ledger PDF export with party filters
</details>

---

## Project Structure

```
CWMS/
├── manage.py
├── requirements.txt
├── Procfile                     # gunicorn for Render
├── build.sh / render_setup.sh   # migrate + collectstatic
├── .env.example
├── docker-compose.yml
├── populate_database.py         # demo data seeder
├── config/                      # settings, URLs, wsgi, cache_utils
├── analytics/                   # audit history + CSV/PDF exports
├── attendance/                  # daily tracking + bulk UI
├── billing/                     # vendor bill management
├── employees/                   # employee master + role management
├── expenses/                    # daily expenses + 7-day lock
├── king/                        # owner dashboard, work orders, ledger
├── leaves/                      # leave policy, allocation, PDF letters
├── payroll/                     # payroll engine + FIFO advances + payslips
├── portal/                      # worker and manager portal views
├── static/                      # CSS, JS, fonts (WhiteNoise served)
├── media/                       # uploaded bills and documents
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Redis 7+ (optional - falls back to DummyCache)
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
# Edit .env - set SECRET_KEY, DATABASE_URL, REDIS_URL

# 5. Migrate
python manage.py migrate

# 6. Create superuser (becomes Owner/Admin)
python manage.py createsuperuser
# Managers and workers are created via Django admin or app flows

# 7. (Optional) Seed demo data
python populate_database.py

# 8. Run
python manage.py runserver
```

### Docker

```bash
docker-compose up --build
# Update .env.docker for credentials before running
```

### Environment Variables

```env
SECRET_KEY=replace-with-a-strong-secret-key
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
CSRF_TRUSTED_ORIGINS=http://localhost:8000
REDIS_URL=redis://127.0.0.1:6379/1

# Optional - used in PDF exports
BRAND_COMPANY_NAME=Your Company Name
BRAND_ACCOUNT_NAME=YOUR COMPANY NAME
BRAND_COMPANY_ADDRESS=
BRAND_COMPANY_GSTIN=
```

---

## API Reference

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

> **Note:** Employee detail endpoints currently check authentication but do not enforce manager-only access. Lock these down before exposing to untrusted clients.

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

## URL Endpoints

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
<summary><strong>Manager - Attendance & Payroll</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/portal/manager/dashboard/` | Manager dashboard |
| GET/POST | `/portal/manager/attendance/bulk/` | Bulk attendance entry |
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
| GET/POST | `/manager/expenses/edit/<id>/` | Edit (7-day lock) |
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
| GET | `/portal/attendance/` | View attendance |
| GET | `/portal/download-payslip/<salary_id>/` | Download payslip |
</details>

<details>
<summary><strong>King (Owner) & Audit</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/king/dashboard/` | Business analytics |
| GET | `/king/workorders/` | Work orders |
| GET | `/king/revenue/` | Revenue dashboard |
| GET | `/king/ledger/` | Ledger view |
| GET | `/king/ledger/pdf/` | Ledger PDF |
| GET | `/king/accounts/` | Account list |
| GET | `/king/audit/` | Full audit history |
| GET | `/king/audit/export/csv/` | Audit CSV |
| GET | `/king/audit/export/pdf/` | Audit PDF |
| GET | `/portal/manager/audit/` | Manager audit history |
</details>

---

## Deployment

### CI/CD (GitHub Actions)

```
push to main
  -> pip install -r requirements.txt
  -> python manage.py check
  -> python manage.py test
  -> auto-deploy to Render
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

### Production Checklist (before go-live)

- [ ] `DEBUG=False` and a strong `SECRET_KEY` in environment
- [ ] `REDIS_URL` set with correct DB index; verify `CACHES` in `settings.py` matches
- [ ] Route `cwms.cache` logger to Sentry or file for Redis failure alerts
- [ ] Set Redis `maxmemory` and eviction policy for your cache footprint
- [ ] Lock down `/api/employees/<id>/` to manager-only access
- [ ] Configure AWS S3 or Cloudflare R2 for media file storage

---

## Future Enhancements

- [ ] Multi-site support (one instance, multiple contractor clients)
- [ ] SMS notifications for payslip delivery
- [ ] Biometric attendance integration
- [ ] Mobile app (React Native)
- [ ] Budget tracking and forecasting
- [ ] Tax and compliance automation

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2c5364,100:0f2027&height=100&section=footer" width="100%"/>

*Built to solve real problems for real contractors - not a demo project.*

</div># CWMS - Contractor Workforce Management System

[![CI](https://github.com/Subham-Singh-Dev/cwms/actions/workflows/ci.yml/badge.svg)](https://github.com/Subham-Singh-Dev/cwms/actions)
[![Live](https://img.shields.io/badge/Live-cwms--1fdo.onrender.com-00b37e?style=flat-square&logo=render&logoColor=white)](https://cwms-1fdo.onrender.com/portal/login/)
[![API Docs](https://img.shields.io/badge/API_Docs-Swagger_UI-85EA2D?style=flat-square&logo=swagger&logoColor=black)](https://cwms-1fdo.onrender.com/api/docs/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?style=flat-square&logo=django&logoColor=white)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

CWMS is a Django monolith for day-wage workforce operations: attendance, payroll,
advances, expenses, billing, audit, and owner analytics.

## Live Links

| | URL |
|---|---|
| Web App | https://cwms-1fdo.onrender.com/portal/login/ |
| API Docs | https://cwms-1fdo.onrender.com/api/docs/ |

## Problem It Solves

CWMS centralizes daily attendance, monthly payroll, advances, expenses, and
owner reporting into one system so managers can run operations without manual
spreadsheets and owners can see cash flow and liabilities in one place.

## Architecture

```
Client
  - Django templates + JS
  - Small JWT API for mobile/automation
        |
        v
Django 5.2 Monolith
  - employees  attendance  payroll  portal
  - expenses   billing     analytics king leaves
        |
        v
Database (SQLite or Postgres) + Redis (optional)
```

## Key Engineering Decisions

- FIFO advance recovery under transaction safety using select_for_update.
- Salary snapshots are immutable after generation (paid flag is separate).
- Role-based access control with strict Manager and King isolation.
- 7-day edit lock for expenses to protect accounting closure.
- Audit trail is append-only and exportable for compliance.
- Leave assignment is blocked when salary for the month is already paid.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | Django 5.2 + Django REST Framework |
| Database | SQLite (dev) or Postgres via DATABASE_URL |
| Auth | Sessions for portal, JWT for API |
| API Docs | drf-spectacular (Swagger) |
| PDF | xhtml2pdf |
| Cache | django-redis with DummyCache fallback |
| Deployment | Gunicorn + WhiteNoise |

## Roles and Access Control

CWMS supports three groups: Worker, Manager, King.

- Manager group: `Manager`
- King group: `King`
- Worker group exists for labeling and data seeding

Access gates are enforced by Manager and King group checks. Worker access is
based on being authenticated, not in Manager/King, and having an Employee
profile.

Login pages:

- Worker/Manager login (single page with toggle): `/portal/login/`
  - Worker login uses phone number + password
  - Manager login uses username + password
- King login: `/king/secure/owner-x7k2/` (sets `king_authenticated` session flag)

## Features

### Payroll

- Monthly salary generation from attendance.
- FIFO advance deduction with row locks inside a transaction.
- PF and ESIC deductions based on employee flags and rates.
- Salary snapshot stores PF and ESIC rate used for audit.
- Mark-paid workflow and CSV export for monthly registers.

### Attendance

- Daily P/H/A/L status with overtime hours.
- Bulk attendance UI for managers.
- Model rules: current-month only; future dates allowed only for approved leave.
- Overtime allowed only when status is Present.

### Advances

- Issue advances to active employees.
- Advance register with outstanding and settled filters.

### Employees

- Employee master data with statutory fields (PF, ESIC, bank, IDs).
- Auto-generated system username (EMPxxxxx) on creation.
- Worker login via phone number and password.

### Leave Management

- Annual leave policy per employment type.
- Leave allocation and usage tracking per year.
- Assigning leave creates attendance rows with status L.
- Leave is blocked if salary for the month is already paid.
- Leave sanction letter PDF export.

### Expenses

- Categories: Food, Fuel, Travel, Material, Misc.
- Payment modes: Cash, UPI, Bank.
- 7-day edit/delete lock.
- CSV and PDF export.

### Billing

- Bill uploads with optional PDF.
- GST calculated at 18 percent.
- Partial payments supported; paid status derived from remaining balance.
- Debtor and client bill types.

### Audit and Analytics

- Audit logs for attendance, payroll, advances, expenses, bills, revenue, and
  work orders.
- Manager audit view is scoped; owner sees full history.
- CSV and PDF exports for audit trails.

### Owner (King)

- Owner dashboard KPIs for payroll, expenses, revenue, liability, and attendance.
- Work orders, manual revenue register, ledger accounts, and ledger entries.
- Ledger PDF export with party filters.

## API (JWT)

Token endpoints:

- POST `/api/token/`
- POST `/api/token/refresh/`

Resources (JWT required):

- GET/POST `/api/attendance/` (manager-only)
- GET `/api/employees/` (manager-only)
- GET `/api/employees/<id>/` (authenticated)
- PUT `/api/employees/<id>/` (authenticated)
- DELETE `/api/employees/<id>/` (authenticated)
- GET `/api/payroll/?month=YYYY-MM` (manager-only)
- GET/POST `/api/advances/` (manager-only)
- GET `/api/activity/` (manager-only)

Note: The employee detail endpoints currently check authentication but do not
enforce manager role. Lock these down before exposing to untrusted clients.

## URL Endpoints (Primary)

- `/portal/login/` worker/manager login
- `/portal/dashboard/` worker dashboard
- `/portal/manager/dashboard/` manager dashboard
- `/portal/manager/attendance/bulk/` bulk attendance
- `/portal/manager/run-payroll/` payroll batch
- `/payroll/summary/` payroll summary
- `/payroll/manager/payroll/salaries/` salary list
- `/manager/employees/` employee list
- `/manager/expenses/` expense dashboard
- `/manager/billing/` billing dashboard
- `/king/secure/owner-x7k2/` owner login
- `/king/dashboard/` owner dashboard

## Caching (Redis)

- Uses django-redis when `REDIS_URL` is set; DummyCache fallback otherwise.
- Key prefix is `cwms` and keys are versioned by Django cache settings.
- Dashboards and API responses are cached for 5 minutes by default; heavier
  lists are cached for 1 hour.
- Cache invalidation is centralized in `config/cache_utils.py` with batched
  delete patterns.

## Setup (Local)

1. Create a virtual environment and install dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

2. Configure environment:

```bash
copy .env.example .env
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Create a superuser:

```bash
python manage.py createsuperuser
```

5. Start the server:

```bash
python manage.py runserver
```

## Environment Variables

```env
SECRET_KEY=replace-with-a-strong-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
DATABASE_URL=sqlite:///db.sqlite3
REDIS_URL=redis://127.0.0.1:6379/1
```

## Docker

```bash
docker-compose up --build
```

This starts Postgres, Redis, and the app (gunicorn). Update `.env.docker` for
credentials.

## Scripts

- `populate_database.py` seeds demo data.
- `TESTING_SCRIPTS.py` provides an interactive test runner.

Note: Some helper scripts create lowercase groups (`managers`, `kings`). The
runtime checks expect `Manager` and `King`. Ensure the correct groups exist.

## Deployment

- `Procfile` runs gunicorn.
- `build.sh` and `render_setup.sh` run migrations and collect static assets.
- Static files are served via WhiteNoise.