# CWMS — Contractor Workforce Management System

[![CI](https://github.com/Subham-Singh-Dev/cwms/actions/workflows/ci.yml/badge.svg)](https://github.com/Subham-Singh-Dev/cwms/actions)
[![Live](https://img.shields.io/badge/Live-cwms--1fdo.onrender.com-00b37e?style=flat-square&logo=render&logoColor=white)](https://cwms-1fdo.onrender.com/portal/login/)
[![API Docs](https://img.shields.io/badge/API_Docs-Swagger_UI-85EA2D?style=flat-square&logo=swagger&logoColor=black)](https://cwms-1fdo.onrender.com/api/docs/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?style=flat-square&logo=django&logoColor=white)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

> A production-grade Django backend that automates daily-wage workforce management for construction contractors. Live system managing 100–500+ workers for a real client.

---

## Live Links

| | URL |
|---|---|
| **Web App** | https://cwms-1fdo.onrender.com/portal/login/ |
| **API Docs (Swagger)** | https://cwms-1fdo.onrender.com/api/docs/ |

---

## The Problem It Solves

| Before CWMS | After CWMS |
|---|---|
| 6–8 hours of manual payroll every month | Payroll processed in under 10 minutes |
| 5–10% advance leakage from manual tracking | Zero leakage — FIFO auto-deduction |
| Frequent wage disputes with workers | Workers trust printed, signed payslips |
| Zero financial visibility for the owner | Real-time liability and cash flow dashboard |

---

## Table of Contents

- [Architecture](#architecture)
- [Key Engineering Decisions](#key-engineering-decisions)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [User Roles](#user-roles)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [API Reference](#api-reference)
- [URL Endpoints](#url-endpoints)
- [Authentication](#authentication)
- [Deployment](#deployment)
- [Future Enhancements](#future-enhancements)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│         Django Templates + Vanilla JS  │  REST API (JWT)    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                      Django 5.2 Backend                      │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │
│  │employees │  │attendance│  │ payroll  │  │  billing  │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │
│  │ expenses │  │  portal  │  │   king   │  │analytics  │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘   │
│                                                              │
│         transaction.atomic() + select_for_update()           │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   PostgreSQL (Render Managed)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Engineering Decisions

These are the decisions that make CWMS production-safe, not just functional.

**FIFO Advance Deduction with `transaction.atomic()`**

When payroll runs for 100–500+ workers concurrently, naive advance deduction causes race conditions — two payroll runs can read the same outstanding balance simultaneously and both deduct from it, causing double-deduction or missed recovery. CWMS uses `select_for_update()` inside `transaction.atomic()` to row-lock advance records per worker, ensuring FIFO recovery is deterministic with zero leakage.

```python
with transaction.atomic():
    advances = Advance.objects.select_for_update().filter(
        employee=employee, recovered=False
    ).order_by('issued_on')   # FIFO — oldest first
    # deduct from net salary until fully recovered or salary exhausted
```

**3-Role RBAC with IDOR Protection**

All three roles (Manager, Worker, King/Owner) use separate decorators and scoped queryset filters. A worker fetching `/payroll/payslip/<id>/` cannot access another worker's payslip — the view filters by `request.user` before returning any record.

**Immutable Salary Snapshots**

Once a salary is generated and marked paid, its data is snapshotted — future rate changes or attendance edits do not retroactively alter past salaries. Critical for financial auditability.

**7-Day Expense Edit Lock**

Expenses cannot be edited or deleted after 7 days, enforced at the view layer. This prevents retroactive accounting manipulation.

---

## Features

### Payroll Engine
- Monthly salary generation per employee
- FIFO advance deduction (oldest debt recovered first)
- Immutable salary snapshots (audit-safe, no retroactive changes)
- Paid leave logic (first 2 absences per month = paid leave)
- Overtime calculation by role
- CSV export of salary list

### Attendance System
- Daily tracking: Present / Half Day / Absent
- Bulk attendance UI — spreadsheet-style for 100+ workers in one view
- Overtime hours per record
- Validation: blocks future dates and previous-month edits

### Advance Management
- Issue cash loans to workers
- Automatic FIFO recovery during payroll run
- Partial recovery tracking across multiple months
- Real-time outstanding balance displayed per worker

### Employee Management
- Add / edit / deactivate employees
- Auto-generated Employee IDs (`EMPxxxxx`) with temporary password
- Worker login by phone number + password

### Billing Module
- Upload vendor bills (PDF)
- Paid / Unpaid toggle with auto-tracked `paid_on` timestamp
- POST-only mutation safety on delete and status toggle

### Daily Expenses
- Categories: Food, Fuel, Travel, Material, Misc
- Payment modes: Cash, UPI, Bank
- Daily / Weekly / Monthly aggregates
- 7-day edit lock (accounting safety)
- CSV and PDF export

### Document Generation
- PDF payslips via xhtml2pdf
- Expense PDF reports
- Audit trail PDF exports
- CSV exports across payroll, expenses, and audit modules

### Audit Log
- Full activity trail: who did what, when, from which IP
- Scope-aware: King sees all, Manager sees only their own actions
- CSV and PDF export for both roles

### King (Owner) Dashboard
- Aggregate business analytics and cash flow overview
- Work order lifecycle management
- Revenue tracking and ledger management
- Strategic reports for owner-level decision making

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | Django 5.2 + Django REST Framework |
| Database | PostgreSQL (Render Managed) via psycopg2-binary |
| Auth | Session-based (portal) + JWT via djangorestframework-simplejwt (API) |
| API Docs | drf-spectacular (Swagger / OpenAPI 3.0) |
| PDF Generation | xhtml2pdf |
| Financial Arithmetic | Python `Decimal` — zero float errors |
| Transaction Safety | `transaction.atomic()` + `select_for_update()` |
| Frontend | Django Templates + Vanilla JS + CSS3 |
| CI/CD | GitHub Actions → auto-deploy to Render on push to `main` |
| Deployment | Render (web service + managed PostgreSQL) |
| Testing | pytest + pytest-django (60 tests, 50% coverage) |

---

## User Roles

| Role | Access Level | Capabilities |
|---|---|---|
| **Manager** | Operational | Attendance, payroll runs, advances, billing, expenses, employee records |
| **Worker** | Read-only | Own attendance, salary history, payslip download |
| **King (Owner)** | Strategic + Financial | Owner dashboard, work orders, revenue ledger, full audit visibility |

---

## Project Structure

```
CWMS/
├── manage.py
├── requirements.txt
├── .env.example                 # Environment variable template
├── config/                      # Project settings + root URL routing
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── analytics/                   # Audit history views + CSV/PDF exports
├── attendance/                  # Daily attendance tracking + bulk UI
├── billing/                     # Vendor bill management
├── employees/                   # Employee + role management
├── expenses/                    # Daily expense tracking + 7-day lock
├── king/                        # Owner dashboard, work orders, revenue, ledger
├── payroll/                     # Payroll engine + FIFO advances + payslips
├── portal/                      # Worker and manager portal views
├── static/                      # CSS, JS, fonts
├── media/                       # Uploaded bills and documents
└── .github/
    └── workflows/
        └── ci.yml               # CI pipeline (check + test + deploy)
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- SQLite3 (development) or PostgreSQL 14+ (production)
- pip

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/cwms.git
cd cwms

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your SECRET_KEY and database credentials

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser (Manager access)
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

### Environment Variables

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
```

---

## API Reference

Full interactive documentation: **https://cwms-1fdo.onrender.com/api/docs/**

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/token/` | Obtain JWT access + refresh token |
| POST | `/api/token/refresh/` | Refresh expired access token |

Access token: valid 5 minutes. Refresh token: valid 24 hours. All endpoints require `Authorization: Bearer <token>`.

### Resources (JWT Required)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/employees/` | List all active employees |
| GET | `/api/attendance/?date=YYYY-MM-DD` | Attendance records for a date |
| POST | `/api/attendance/` | Mark single attendance record |
| GET | `/api/activity/` | Recent audit activity feed |

### Quick Start

```bash
# Step 1 — Get token
curl -X POST https://cwms-1fdo.onrender.com/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_user", "password": "your_pass"}'

# Step 2 — Use token
curl https://cwms-1fdo.onrender.com/api/employees/ \
  -H "Authorization: Bearer <your_access_token>"
```

---

## URL Endpoints

<details>
<summary><strong>Authentication</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET/POST | `/portal/login/` | Worker / Manager portal login |
| GET | `/portal/logout/` | Portal logout |
| GET/POST | `/king/secure/owner-x7k2/` | King secure login |
| GET | `/king/logout/` | King logout |
</details>

<details>
<summary><strong>Manager & Attendance</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/portal/manager/dashboard/` | Manager dashboard |
| GET | `/portal/manager/dashboard/recent-activity/` | Recent activity JSON |
| GET/POST | `/portal/manager/attendance/bulk/` | Bulk attendance entry |
| POST | `/portal/manager/run-payroll/` | Trigger payroll run |
| GET/POST | `/portal/manager/advances/issue/` | Issue worker advance |
</details>

<details>
<summary><strong>Payroll</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/payroll/summary/` | Payroll batch summary |
| GET | `/payroll/manager/payroll/salaries/` | Salary list |
| POST | `/payroll/manager/payroll/salaries/generate/` | Generate one employee salary |
| POST | `/payroll/manager/payroll/salaries/mark-paid/` | Mark salary paid |
| GET | `/payroll/manager/payroll/salaries/export/` | CSV export |
| GET | `/payroll/payslip/<salary_id>/` | Download payslip (role-scoped) |
</details>

<details>
<summary><strong>Billing, Expenses, Employees</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET/POST | `/manager/billing/` | Billing dashboard / upload |
| POST | `/toggle_bill_status/<bill_id>/` | Toggle paid/unpaid |
| GET/POST | `/manager/expenses/` | Expenses dashboard / add |
| GET/POST | `/manager/expenses/edit/<expense_id>/` | Edit (7-day lock) |
| GET | `/manager/expenses/export/` | CSV export |
| GET | `/manager/expenses/pdf/` | PDF export |
| GET | `/manager/employees/` | Employee list |
| GET/POST | `/manager/employees/add/` | Add employee |
</details>

<details>
<summary><strong>Worker Portal</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/portal/dashboard/` | Worker home |
| GET | `/portal/profile/` | Worker profile |
| GET | `/portal/attendance/` | View attendance |
| GET | `/portal/download-payslip/<salary_id>/` | Download payslip PDF |
</details>

<details>
<summary><strong>King (Owner) & Audit</strong></summary>

| Method | URL | Description |
|---|---|---|
| GET | `/king/dashboard/` | Business analytics overview |
| GET | `/king/workorders/` | Work order dashboard |
| GET | `/king/revenue/` | Revenue dashboard |
| GET | `/king/ledger/` | Ledger view |
| GET | `/king/audit/` | Full audit history |
| GET | `/king/audit/export/csv/` | Audit CSV export |
| GET | `/portal/manager/audit/` | Manager audit history |
</details>

---

## Authentication

**Manager:** Username + password → session cookie → `@manager_required` decorator on all manager views.

**Worker:** Phone number + password → session cookie → `@worker_required` decorator. Read-only access enforced.

**King:** Dedicated secure URL → explicit `King` group check + session flag (`king_authenticated`) → `@king_required` decorator.

**Security measures:**
- CSRF tokens on all forms
- IDOR protection — workers can only access their own payslips
- Role isolation enforced between Manager and King flows
- POST-only enforcement on all critical mutation endpoints
- Full audit log on every financial action (actor, IP, timestamp)

---

## Deployment

### CI/CD Pipeline

GitHub Actions runs on every push to `main`:

```
push to main
    → Install dependencies
    → python manage.py check
    → python manage.py test
    → Auto-deploy to Render on success
```

### Production Stack (Self-Hosted)

```
OS:        Ubuntu 22.04 LTS
Web:       Nginx + Gunicorn
Database:  PostgreSQL 14+
Process:   Systemd
SSL:       Let's Encrypt
RAM:       2GB minimum
Storage:   20GB minimum
```

### Cloud (Current)

Render web service + managed PostgreSQL. Compatible with Railway and DigitalOcean. For media storage at scale: AWS S3 or Cloudflare R2.

---

## Future Enhancements

- [ ] Multi-site support (one instance, multiple contractor clients)
- [ ] SMS notifications for payslip delivery
- [ ] Biometric attendance integration
- [ ] Mobile app (React Native)
- [ ] Budget tracking and forecasting module
- [ ] Tax and compliance automation

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

> Built to solve real problems for real contractors — not a demo project.

