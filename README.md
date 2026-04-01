# 🏗️ CWMS — Contractor Workforce Management System

> A production-grade Django backend system that automates daily-wage workforce management for construction contractors.

---

## 📌 Table of Contents
- [Overview](#overview)
- [Problem It Solves](#problem-it-solves)
- [User Roles](#user-roles)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [URL Endpoints](#url-endpoints)
- [Authentication](#authentication)
- [Deployment](#deployment)
- [Future Enhancements](#future-enhancements)

---

## Overview

CWMS replaces paper registers, Excel sheets, and ad-hoc workflows used by contractors to manage 100-400+ daily-wage workers. It provides a deterministic, auditable payroll workflow with attendance, advances, expenses, billing, owner reporting, and exportable documents.

---

## Problem It Solves

| Before CWMS | After CWMS |
|-------------|------------|
| 6–8 hours of manual payroll | Payroll in 10 minutes |
| 5–10% advance leakage | Zero leakage (FIFO auto-deduction) |
| Frequent wage disputes | Workers trust printed payslips |
| Zero financial visibility | Real-time liability tracking |

---

## User Roles

| Role | Access | Capabilities |
|------|--------|-------------|
| **Manager** | Operational Control | Attendance, payroll actions, advances, billing, expenses, employee records |
| **Worker** | Read-Only | View own attendance, salary, download payslips |
| **King (Owner)** | Strategic + Financial Control | Owner dashboard, work orders, revenue ledger, full audit visibility |

---

## Features

### 📊 Payroll Engine
- Monthly salary generation per employee
- Manager payroll dashboard summary and salary list
- FIFO-based advance deduction (oldest debt first)
- Immutable salary snapshots (audit-safe)
- Paid leave logic (first 2 absences = paid leave)
- Overtime calculation by role
- CSV export of salary list

### 📅 Attendance System
- Daily tracking: Present / Half Day / Absent
- Bulk attendance UI (spreadsheet-style for 100+ workers)
- Overtime hours per record
- Validation rules for future date / previous month marking

### 💰 Advance Management
- Issue cash loans to workers
- Automatic FIFO recovery during payroll
- Partial recovery tracking across months
- Real-time outstanding balance display
- Managed within the `payroll` app — no separate module required

### 👥 Employee Management
- Add/edit/deactivate employees
- Auto-generated user IDs (`EMPxxxxx`) with temporary password
- Role assignment (Worker / Manager)
- Worker login by phone number + password

### 📄 Billing Module
- Upload vendor bills (PDF)
- Mark Paid / Unpaid toggle
- Payment date auto-tracking (`paid_on`)
- Manager-only delete and status toggle with POST-only mutation safety

### 💸 Daily Expenses
- Categories: Food, Fuel, Travel, Material, Misc
- Payment modes: Cash, UPI, Bank
- Daily / Weekly / Monthly aggregates
- 7-day edit lock (accounting safety)
- CSV and PDF export
- POST-only delete action for safer mutation handling

### 📑 Document Generation
- PDF payslips (xhtml2pdf)
- Expense PDF reports
- Audit trail PDF exports
- CSV exports across payroll, expenses, and audit modules

### 🔍 Audit Log
- Full activity trail across all modules (who did what, when)
- Scope-aware views (King full scope, Manager filtered scope)
- Accessible to Manager and King roles
- CSV/PDF exports for both roles

### 👑 King Dashboard
- Aggregate business analytics and cash flow overview
- Work order lifecycle management
- Revenue tracking and ledger management
- Strategic reports for owner-level decision making

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11.x, Django 5.2.x |
| Database (Dev) | SQLite3 |
| Database (Prod) | PostgreSQL (via `psycopg2-binary`) |
| PDF Generation | xhtml2pdf |
| PDF Rendering Compatibility | reportlab `<4` |
| Frontend | Django Templates, Vanilla JS, CSS3 |
| Typography | Inter (Google Fonts) |
| Financial Arithmetic | Python Decimal (zero float errors) |
| Transaction Safety | `transaction.atomic()`, `select_for_update()` |
| CI | GitHub Actions (`manage.py check` + `manage.py test`) |

---

## Project Structure

```
CWMS/
├── manage.py
├── requirements.txt
├── .env.example                # Environment template
├── db.sqlite3                  # Local development database
├── config/                     # Project config + root URL routing
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── analytics/                  # Audit history views + CSV/PDF exports
├── attendance/                 # Daily attendance tracking models
├── billing/                    # Vendor bill management
├── employees/                  # Employee + role management
├── expenses/                   # Daily expense tracking
├── king/                       # Owner dashboard, workorders, revenue, ledger
├── payroll/                    # Payroll engine + advances + payslip export
├── portal/                     # Worker and manager portal views
├── static/                     # CSS, JS, fonts
├── media/                      # Uploaded bills/documents
└── .github/workflows/ci.yml    # CI pipeline
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- SQLite3 (development) or PostgreSQL (production)
- pip

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/cwms.git
cd CWMS

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
# Edit .env with your database credentials and SECRET_KEY

# 5. Run migrations
python manage.py migrate

# 6. Create superuser (Manager)
python manage.py createsuperuser

# 7. Run development server
python manage.py runserver
```

### Environment Variables (.env)
```
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
```

---

## URL Endpoints

### Authentication
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/portal/login/` | Worker/Manager portal login |
| GET | `/portal/logout/` | Worker/Manager portal logout |
| GET/POST | `/king/secure/owner-x7k2/` | King secure login |
| GET | `/king/logout/` | King logout |

### Employees
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/manager/employees/` | Employee list with filters |
| GET/POST | `/manager/employees/add/` | Add employee + create linked user |
| GET/POST | `/manager/employees/edit/<employee_id>/` | Edit employee |

### Manager
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/portal/manager/dashboard/` | Manager dashboard |
| GET | `/portal/manager/dashboard/recent-activity/` | Recent activity JSON feed |
| GET/POST | `/portal/manager/attendance/bulk/` | Bulk attendance entry |
| POST | `/portal/manager/run-payroll/` | Trigger month payroll run |
| GET/POST | `/portal/manager/advances/issue/` | Issue worker advance |

### Payroll
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/payroll/summary/` | Payroll batch summary |
| GET | `/payroll/manager/payroll/salaries/` | Salary list for selected month |
| POST | `/payroll/manager/payroll/salaries/generate/` | Generate one employee salary |
| POST | `/payroll/manager/payroll/salaries/mark-paid/` | Mark salary paid |
| GET | `/payroll/manager/payroll/salaries/export/` | Salary CSV export |
| GET | `/payroll/payslip/<salary_id>/` | Payslip download (role scoped) |

### Billing
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/manager/billing/` | Billing dashboard / upload bill |
| POST | `/toggle_bill_status/<bill_id>/` | Toggle paid/unpaid |
| POST | `/delete_bill/<bill_id>/` | Delete bill |

### Expenses
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/manager/expenses/` | Expenses dashboard / add expense |
| GET/POST | `/manager/expenses/edit/<expense_id>/` | Edit expense (7-day lock) |
| POST | `/manager/expenses/delete/<expense_id>/` | Delete expense (POST-only) |
| GET | `/manager/expenses/export/` | CSV export |
| GET | `/manager/expenses/pdf/` | PDF export |

### Worker Portal
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/portal/dashboard/` | Worker home |
| GET | `/portal/profile/` | Worker profile |
| GET | `/portal/attendance/` | View attendance |
| GET | `/portal/download-payslip/<salary_id>/` | Download payslip PDF |

### King (Owner)
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/king/dashboard/` | Business analytics overview |
| GET | `/king/dashboard/recent-activity/` | Recent activity JSON feed |
| GET | `/king/workorders/` | Work order dashboard |
| GET/POST | `/king/workorders/add/` | Add work order |
| GET | `/king/workorders/<wo_id>/` | Work order detail |
| GET/POST | `/king/workorders/<wo_id>/edit/` | Edit work order |
| POST | `/king/workorders/<wo_id>/status/` | Update work order status |
| GET | `/king/revenue/` | Revenue dashboard |
| POST | `/king/revenue/add/` | Add revenue entry |
| POST | `/king/revenue/delete/<rev_id>/` | Delete revenue entry |
| GET | `/king/ledger/` | Ledger view |
| POST | `/king/ledger/add/` | Add ledger entry |
| POST | `/king/ledger/delete/<entry_id>/` | Delete ledger entry |
| GET | `/king/ledger/pdf/` | Ledger PDF export |

### Audit History
| Method | URL | Description |
|--------|-----|-------------|
| GET | `/king/audit/` | King audit history page |
| GET | `/king/audit/export/csv/` | King audit CSV export |
| GET | `/king/audit/export/pdf/` | King audit PDF export |
| GET | `/portal/manager/audit/` | Manager audit history page |
| GET | `/portal/manager/audit/export/csv/` | Manager audit CSV export |
| GET | `/portal/manager/audit/export/pdf/` | Manager audit PDF export |

---

## Authentication

**Manager Login:** Portal login (username + password path), session-based, protected by `@manager_required` decorator.

**Worker Login:** Phone number + password via portal login. Worker access is read-only and enforced via `@worker_required`.

**King Login:** Dedicated secure URL with explicit `King` group checks and session flag (`king_authenticated`), enforced via `@king_required`.

**Security:**
- CSRF tokens on all forms
- IDOR protection for worker payslip access
- Session-based auth with Django password hashing
- Role-isolation guards between Manager and King flows
- POST-only enforcement on critical mutation endpoints
- Full audit log for critical operations + export actions

---

## Deployment

### Recommended Stack (Production)
```
OS:       Ubuntu 22.04 LTS
Web:      Nginx + Gunicorn
Database: PostgreSQL 14+
Process:  Systemd
SSL:      Let's Encrypt
RAM:      2GB minimum
Storage:  20GB minimum
```

### Cloud Option
Railway / Render / DigitalOcean with managed PostgreSQL and AWS S3 / Cloudflare R2 for media storage.

### CI Pipeline
- GitHub Actions workflow (`.github/workflows/ci.yml`)
- Runs on pushes and pull requests to `main`
- Steps:
	- Install dependencies
	- `python manage.py check`
	- `python manage.py test`

---

## Future Enhancements

- Multi-site support
- SMS notifications for payslips
- Biometric attendance integration
- Mobile app (React Native)
- Budget tracking module
- Tax / compliance automation

---

## 📜 License

This project is licensed under the MIT License.

---

> Built with ❤️ to solve real problems for real contractors.
