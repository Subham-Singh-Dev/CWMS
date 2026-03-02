🏗️ CWMS — Contractor Workforce Management System

A production-grade Django backend system that automates daily-wage workforce management for construction contractors.


📌 Table of Contents

Overview
Problem It Solves
User Roles
Features
Tech Stack
Project Structure
Setup & Installation
URL Endpoints
Authentication
Deployment
Future Enhancements


Overview
CWMS replaces paper registers, Excel sheets, and WhatsApp notes used by local contractors to manage 50–200+ daily-wage workers. It provides a deterministic, auditable, rule-based payroll engine with full financial visibility.

Problem It Solves
Before CWMSAfter CWMS6–8 hours of manual payrollPayroll in 10 minutes5–10% advance leakageZero leakage (FIFO auto-deduction)Frequent wage disputesWorkers trust printed payslipsZero financial visibilityReal-time liability tracking

User Roles
RoleAccessCapabilitiesManagerFull ControlAttendance, payroll, advances, billing, expensesWorkerRead-OnlyView own attendance, salary, download payslipsKing (Owner)Strategic ViewBusiness analytics, cash flow, aggregate reports, inventory

Features
📊 Payroll Engine

Monthly & bulk payroll generation
Mid-month salary generation for individual employees (on-demand, partial payout)
FIFO-based advance deduction (oldest debt first)
Immutable salary snapshots (audit-safe)
Paid leave logic (first 2 absences = paid leave)
Overtime calculation by role

📅 Attendance System

Daily tracking: Present / Half Day / Absent
Bulk attendance UI (spreadsheet-style for 100+ workers)
Overtime hours per record
Historical view for any past date

💰 Advance Management

Issue cash loans to workers
Automatic FIFO recovery during payroll
Partial recovery tracking across months
Real-time outstanding balance display
Managed within the payroll app — no separate module required

👥 Employee Management

Add/deactivate employees
Auto-generated employee codes
Role assignment (Worker / Manager)
Worker login credentials (phone number + password) assigned by superuser or manager

📄 Billing Module

Upload vendor bills (PDF)
Mark Paid / Unpaid toggle
Auto-generated bill numbers (BILL-001 format)
CSV export for accountants

💸 Daily Expenses

Categories: Food, Fuel, Travel, Material, Misc
Payment modes: Cash, UPI, Bank
Daily / Weekly / Monthly aggregates
7-day edit lock (accounting safety)
CSV and PDF export

📑 Document Generation

PDF payslips (xhtml2pdf)
Expense PDF reports
CSV exports across all modules

🔍 Audit Log

Full activity trail across all modules (who did what, when)
Tamper-proof log entries for payroll, advances, and attendance changes
Accessible to Manager and King roles

👑 King Dashboard

Aggregate business analytics and cash flow overview
Cross-site financial visibility (future: multi-site)
Inventory management integration
Strategic reports for owner-level decision making

📦 Inventory Management

Track materials and equipment on-site
Stock-in / stock-out records
Low stock alerts
Linked to daily expenses for material cost tracking


Tech Stack
LayerTechnologyBackendPython 3.10+, Django 4.x/5.xDatabase (Dev)SQLite3Database (Prod)PostgreSQLPDF Generationxhtml2pdfFrontendDjango Templates, Vanilla JS, CSS3TypographyInter (Google Fonts)Financial ArithmeticPython Decimal (zero float errors)Transaction Safetytransaction.atomic(), select_for_update()

Project Structure
cwms/
├── manage.py
├── requirements.txt
├── worker_data_final.csv       # Seed data for worker import
├── db.sqlite3                  # Development database
├── config/                     # Project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── attendance/                 # Daily attendance tracking
├── billing/                    # Vendor bill management
├── employees/                  # Employee management
├── expenses/                   # Daily expense tracking
├── payroll/                    # Payroll engine, salary logic & advance management
├── portal/                     # Worker portal (read-only, phone + password login)
├── static/                     # CSS, JS, fonts
└── media/                      # Uploaded bills & documents

Setup & Installation
Prerequisites

Python 3.10+
SQLite3 (development) or PostgreSQL (production)
pip

Steps
bash# 1. Clone the repository
git clone https://github.com/yourusername/cwms.git
cd cwms

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your database credentials and SECRET_KEY

# 5. Run migrations
python manage.py migrate

# 6. Create superuser (Manager)
python manage.py createsuperuser

# 7. Run development server
python manage.py runserver
Environment Variables (.env)
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1

URL Endpoints
Authentication
MethodURLDescriptionPOST/worker_login/Worker login (phone number + password)POST/manager_login/Manager loginPOST/logout/Logout
Manager
MethodURLDescriptionGET/manager/dashboard/Manager dashboardGET/POST/manager/employees/List / add employeesGET/POST/manager/attendance/bulk/Bulk attendancePOST/manager/payroll/generate/Generate payrollPOST/manager/payroll/generate/mid-month/<id>/Mid-month salary for individual employeeGET/manager/payroll/summary/Payroll summaryGET/manager/salary-list/Salary listPOST/manager/salary/mark-paid/<id>/Mark salary paidPOST/manager/advance/add/Issue advance
Billing
MethodURLDescriptionGET/POST/billing/Dashboard / upload billPOST/billing/toggle/<id>/Toggle paid statusGET/billing/export/csv/Export CSV
Expenses
MethodURLDescriptionGET/POST/expenses/Dashboard / add expensePOST/expenses/edit/<id>/Edit expense (7-day lock)GET/expenses/export/csv/CSV exportGET/expenses/export/pdf/PDF export
Worker Portal
MethodURLDescriptionGET/portal/dashboard/Worker homeGET/portal/attendance/View attendanceGET/portal/salary/View salary historyGET/portal/payslip/download/<id>/Download payslip PDF
King Dashboard
MethodURLDescriptionGET/king/dashboard/Business analytics overviewGET/king/inventory/Inventory managementGET/king/audit-log/Full audit trail

Authentication
Manager Login: Username + Password (Django default auth), session-based, protected by @manager_required decorator.
Worker Login: Phone number + Password — credentials are created and assigned by the superuser or manager. Read-only access enforced at the view level via the portal app.
King Login: Superuser-level credentials, session-based, protected by @king_required decorator.
Security:

CSRF tokens on all forms
IDOR protection (users access only their own data)
Password hashing (pbkdf2_sha256)
Session hijacking prevention
No sensitive data in URLs
Full audit log for all critical actions


Deployment
Recommended Stack (Production)
OS:       Ubuntu 22.04 LTS
Web:      Nginx + Gunicorn
Database: PostgreSQL 14+
Process:  Systemd
SSL:      Let's Encrypt
RAM:      2GB minimum
Storage:  20GB minimum
Cloud Option
Railway / Render / DigitalOcean with managed PostgreSQL and AWS S3 / Cloudflare R2 for media storage.

Future Enhancements

Multi-site support
SMS notifications for payslips
Biometric attendance integration
Mobile app (React Native)
Budget tracking module
Tax / compliance automation


📜 License
This project is licensed under the MIT License.


Built with ❤️ to solve real problems for real contractors.