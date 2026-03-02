# 📡 CWMS — URL & View Reference

> CWMS is a Django template-based system (no REST framework). This document covers all URL endpoints, request parameters, access control, and responses.

---

## 📌 Table of Contents
- [Authentication](#authentication)
- [Manager Views](#manager-views)
- [Attendance](#attendance)
- [Payroll & Advances](#payroll--advances)
- [Billing](#billing)
- [Expenses](#expenses)
- [Worker Portal](#worker-portal)
- [King Dashboard](#king-dashboard)
- [Audit Log](#audit-log)
- [Inventory](#inventory)
- [Access Control Summary](#access-control-summary)

---

## 🔐 Authentication

### `POST /manager_login/`
Logs in a Manager using Django's default auth system.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | Manager username |
| `password` | string | ✅ | Manager password |

**Success:** Redirects to `/manager/dashboard/`
**Failure:** Returns login page with error message

---

### `POST /worker_login/`
Logs in a Worker using phone number + password.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone` | string | ✅ | Worker's registered phone number |
| `password` | string | ✅ | Password assigned by Manager/Superuser |

**Success:** Redirects to `/portal/dashboard/`
**Failure:** Returns login page with error message

---

### `POST /logout/`
Logs out the current session (any role).

**Success:** Redirects to login page

---

## 👷 Manager Views

### `GET /manager/dashboard/`
Returns the Manager dashboard with summary cards.

**Access:** Manager only (`@manager_required`)
**Returns:** Active employees count, today's attendance summary, pending advances, unpaid bills

---

### `GET /manager/employees/`
Lists all active employees.

**Access:** Manager only
**Returns:** Employee list with name, code, role, phone, daily wage

---

### `POST /manager/employees/`
Adds a new employee.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Full name |
| `phone` | string | ✅ | Phone number (used for worker login) |
| `daily_wage` | decimal | ✅ | Daily wage amount |
| `role` | string | ✅ | `worker` or `manager` |
| `password` | string | ✅ | Login password for worker |

**Success:** Redirects to employee list with success message

---

### `POST /manager/employees/deactivate/<id>/`
Deactivates an employee (soft delete).

| Param | Type | Description |
|-------|------|-------------|
| `id` | int | Employee ID |

**Access:** Manager only
**Success:** Employee marked inactive, removed from active lists

---

## 📅 Attendance

### `GET /manager/attendance/bulk/`
Returns the bulk attendance entry page for today.

**Access:** Manager only
**Returns:** Spreadsheet-style grid of all active employees

---

### `POST /manager/attendance/bulk/`
Submits attendance for multiple employees at once.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `employee_id` | int | ✅ | Employee ID |
| `status` | string | ✅ | `present`, `half_day`, `absent` |
| `overtime_hours` | decimal | ❌ | Overtime hours worked |
| `date` | date | ✅ | Attendance date (YYYY-MM-DD) |

**Success:** Saves attendance records, redirects with success message

---

### `GET /manager/attendance/history/`
View attendance for any past date.

| Query Param | Type | Description |
|-------------|------|-------------|
| `date` | date | Date to view (YYYY-MM-DD) |
| `employee_id` | int | Filter by employee (optional) |

---

## 💰 Payroll & Advances

### `POST /manager/payroll/generate/`
Generates monthly payroll for all active employees.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `month` | int | ✅ | Month (1–12) |
| `year` | int | ✅ | Year (e.g. 2025) |

**Logic Applied:**
- Counts present / half-day / absent days
- First 2 absences treated as paid leave
- Overtime calculated by role rate
- Advances deducted via FIFO (oldest first)
- Immutable snapshot saved

**Access:** Manager only
**Success:** Redirects to payroll summary

---

### `POST /manager/payroll/generate/mid-month/<id>/`
Generates a partial salary for a single employee mid-month.

| Param | Type | Description |
|-------|------|-------------|
| `id` | int | Employee ID |

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `payout_date` | date | ✅ | Date of mid-month payment |
| `amount` | decimal | ✅ | Amount to pay out |

**Access:** Manager only
**Success:** Creates partial salary record, deducts from end-of-month calculation

---

### `GET /manager/payroll/summary/`
Shows payroll summary for a given month.

| Query Param | Type | Description |
|-------------|------|-------------|
| `month` | int | Month (1–12) |
| `year` | int | Year |

**Returns:** Per-employee breakdown — days worked, overtime, advances deducted, net salary

---

### `GET /manager/salary-list/`
Lists all generated salary records.

**Returns:** Employee name, gross salary, deductions, net salary, paid status

---

### `POST /manager/salary/mark-paid/<id>/`
Marks a salary record as paid.

| Param | Type | Description |
|-------|------|-------------|
| `id` | int | Salary record ID |

**Access:** Manager only
**Success:** Updates paid status, records payment timestamp

---

### `POST /manager/advance/add/`
Issues a cash advance to an employee.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `employee_id` | int | ✅ | Employee ID |
| `amount` | decimal | ✅ | Advance amount |
| `date` | date | ✅ | Issue date |
| `note` | string | ❌ | Optional reason/note |

**Access:** Manager only
**Logic:** Advance saved with timestamp for FIFO recovery during payroll
**Success:** Redirects with outstanding balance updated

---

## 📄 Billing

### `GET /billing/`
Returns billing dashboard with all vendor bills.

**Access:** Manager only
**Returns:** Bill list with number, vendor, amount, status, upload date

---

### `POST /billing/`
Uploads a new vendor bill.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vendor_name` | string | ✅ | Vendor / supplier name |
| `amount` | decimal | ✅ | Bill amount |
| `bill_file` | file (PDF) | ✅ | Scanned bill (PDF only) |
| `date` | date | ✅ | Bill date |

**Success:** Auto-generates bill number (BILL-001 format), saves to media/

---

### `POST /billing/toggle/<id>/`
Toggles bill payment status between Paid and Unpaid.

| Param | Type | Description |
|-------|------|-------------|
| `id` | int | Bill ID |

**Success:** Flips status, records timestamp if marking paid

---

### `GET /billing/export/csv/`
Exports all bills as a CSV file.

| Query Param | Type | Description |
|-------------|------|-------------|
| `status` | string | Filter: `paid`, `unpaid`, `all` (default: all) |

**Returns:** Downloadable `.csv` file

---

## 💸 Expenses

### `GET /expenses/`
Returns expense dashboard with daily/weekly/monthly aggregates.

**Access:** Manager only
**Returns:** Expense list, totals by category and payment mode

---

### `POST /expenses/`
Adds a new daily expense.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | string | ✅ | `food`, `fuel`, `travel`, `material`, `misc` |
| `amount` | decimal | ✅ | Expense amount |
| `payment_mode` | string | ✅ | `cash`, `upi`, `bank` |
| `date` | date | ✅ | Expense date |
| `note` | string | ❌ | Optional description |

**Success:** Saves record, updates aggregates

---

### `POST /expenses/edit/<id>/`
Edits an existing expense (7-day lock enforced).

| Param | Type | Description |
|-------|------|-------------|
| `id` | int | Expense ID |

**Lock Rule:** Expenses older than 7 days cannot be edited
**Access:** Manager only

---

### `GET /expenses/export/csv/`
Exports expenses as CSV.

| Query Param | Type | Description |
|-------------|------|-------------|
| `from` | date | Start date |
| `to` | date | End date |

---

### `GET /expenses/export/pdf/`
Exports expenses as a PDF report.

| Query Param | Type | Description |
|-------------|------|-------------|
| `from` | date | Start date |
| `to` | date | End date |

**Returns:** Downloadable PDF with expense summary and totals

---

## 👷 Worker Portal

### `GET /portal/dashboard/`
Worker home page showing summary of their own data.

**Access:** Authenticated worker only (`@worker_required`)
**Returns:** Name, employee code, current month attendance summary, outstanding advance balance

---

### `GET /portal/attendance/`
Worker's own attendance history.

| Query Param | Type | Description |
|-------------|------|-------------|
| `month` | int | Month filter (optional) |
| `year` | int | Year filter (optional) |

**Returns:** Day-by-day attendance status for the worker

---

### `GET /portal/salary/`
Worker's salary history.

**Returns:** Month-wise salary records — gross, deductions, net, paid status

---

### `GET /portal/payslip/download/<id>/`
Downloads a PDF payslip for a specific salary record.

| Param | Type | Description |
|-------|------|-------------|
| `id` | int | Salary record ID |

**Access:** Worker can only download their own payslips (IDOR protected)
**Returns:** Generated PDF payslip via xhtml2pdf

---

## 👑 King Dashboard

### `GET /king/dashboard/`
Business analytics overview for the owner.

**Access:** King (superuser) only (`@king_required`)
**Returns:** Total payroll liability, advance outstanding, monthly expense trends, cash flow summary

---

### `GET /king/inventory/`
Inventory management view.

**Returns:** Stock list with item name, quantity, unit, last updated

---

### `GET /king/audit-log/`
Full activity audit trail across all modules.

| Query Param | Type | Description |
|-------------|------|-------------|
| `user` | string | Filter by username (optional) |
| `action` | string | Filter by action type (optional) |
| `from` | date | Start date (optional) |
| `to` | date | End date (optional) |

**Returns:** Timestamped log of all critical actions (payroll generation, advance issuance, attendance edits, bill uploads)

---

## 🔒 Access Control Summary

| URL Pattern | Manager | Worker | King |
|-------------|---------|--------|------|
| `/manager/*` | ✅ | ❌ | ✅ |
| `/portal/*` | ❌ | ✅ | ❌ |
| `/king/*` | ❌ | ❌ | ✅ |
| `/billing/*` | ✅ | ❌ | ✅ |
| `/expenses/*` | ✅ | ❌ | ✅ |

---

## 🛡️ Security Notes

- All forms protected with **CSRF tokens**
- Workers can only access **their own data** (IDOR protection at view level)
- Passwords hashed with **pbkdf2_sha256**
- Session-based auth — no tokens/JWT
- No sensitive data exposed in URLs
- All critical actions recorded in **Audit Log**

---

> 📌 This is a Django template-based system. All endpoints return HTML pages unless explicitly noted as CSV/PDF exports.
