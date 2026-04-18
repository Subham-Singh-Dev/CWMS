# FEATURES SUMMARY - CWMS

## 🚀 Executive Summary
CWMS (Contractor Workforce Management System) is an end-to-end business platform built for contractors who manage daily-wage teams, monthly payouts, and project cash flow.
It brings attendance, payroll, advances, expenses, billing, and owner-level financial oversight into one connected system.
The software reduces manual errors, saves admin time, and gives both managers and owners a reliable daily operating view.
It is designed for real contractor operations where speed, accountability, and payment accuracy matter.
CWMS also provides export-ready reports (CSV and PDF) for documentation, client sharing, and compliance needs.

---

## 👤 User Roles

### Manager
- Runs day-to-day operations from a single dashboard, including attendance, payroll, employee management, advances, expenses, and billing.
- Uses bulk workflows to save time and can quickly track liabilities, pending payments, and monthly summaries.

### Worker
- Logs in securely to view only personal records, including attendance history and salary information.
- Can download own payslips after payment is marked, improving transparency and trust.

### King (Owner)
- Gets a strategic financial control center with full visibility into revenue, liabilities, work orders, and ledger movement.
- Can also open the manager console in owner-view mode to monitor operations without changing role boundaries.

---

## 🧭 Portal Module (Core Access and Dashboards)

### Role-based login flow
The login experience supports manager and worker access modes so each user gets the right interface immediately. This reduces confusion and keeps operations secure.

### Manager dashboard command center
The manager dashboard shows key payroll and workforce metrics, quick actions, and recent activity in one screen. This helps managers act faster without jumping between pages.

### Owner-view inside manager console
When the owner opens the manager console, the system clearly marks owner access mode and keeps navigation context visible. This enables oversight while maintaining clarity of responsibility.

### Worker self-service view
Workers can see their own attendance and salary records in a simple format. This cuts repetitive admin queries and improves payment transparency.

### Live operational activity feed
Recent actions are surfaced in dashboard activity panels. This gives immediate visibility into what changed and when.

---

## 👥 Employees Module

### Employee master records
The system stores complete worker profiles including role, wage, join date, contact, and compliance details. This creates one reliable source for payroll and reporting.

### Employment classification
Workers can be marked as Local or Permanent with statutory applicability controls. This ensures correct compliance behavior and clean payroll rules.

### PF and ESIC profile settings
PF and ESIC applicability and rates are stored per employee. This enables accurate deductions based on each worker’s legal profile.

### Active and inactive worker control
Employees can be deactivated without deleting history. This protects records while preventing inactive workers from entering new payroll runs.

### Employee list with filters and search
Managers can quickly filter and search workers by role, status, employment type, and ID fields. This speeds up daily HR and payroll prep work.

### CSV employee import support
Bulk import capability reduces onboarding effort when many workers must be added quickly. This is especially useful at project startup or migration.

---

## 📅 Attendance Module

### Daily attendance capture
Managers can mark Present, Absent, or Half Day for each worker. This creates the core input used in salary generation.

### Bulk attendance interface
A bulk attendance screen allows fast row-wise updates for many workers at once. This dramatically reduces daily manual entry time.

### Overtime hour tracking
Overtime can be recorded in decimal hours and is included in payroll calculations. This ensures workers are paid fairly for extra effort.

### Attendance date policy controls
The system restricts invalid attendance periods (such as future dates and locked month boundaries per business rules). This prevents retrospective manipulation and keeps payroll trustworthy.

---

## 💰 Payroll Module

### Monthly payroll generation
Payroll is generated month-wise using attendance, wages, overtime, and deductions. This provides a consistent and repeatable salary process.

### Paid leave rule
The payroll logic includes paid leave handling based on configured business rules, including the first-absences treatment in monthly salary calculations. This reflects contractor policy fairly and consistently.

### FIFO advance deduction
Outstanding advances are deducted using first-in, first-out order. This ensures older dues are cleared first and avoids deduction disputes.

### Statutory deductions (PF and ESIC)
PF and ESIC are computed from employee-specific settings and stored as salary snapshots. This improves legal readiness and avoids recalculation ambiguity later.

### Salary list management
Managers get a detailed salary list with payment status, deduction breakup, and action controls. This makes month-end payout tracking simple and auditable.

### Mark-as-paid workflow
Salary payment status can be updated directly from the management list with paid-on date behavior. This gives a clean operational closure for each payroll cycle.

### Payroll summary and trend view
The summary page provides totals for gross, deductions, net, paid, and pending liability with trend charts. This helps managers explain payroll movement quickly.

### Payslip generation and download
Payslips are generated in PDF format with earning and deduction details. Workers can download own paid slips, reducing manual HR handoffs.

### Salary CSV export
Managers can export salary registers to CSV by month. This supports accounting, reconciliation, and external sharing needs.

---

## 💸 Advances Module (Handled Inside Payroll)

### Advance issuance
Managers can issue advances to active workers with date and amount details. This supports real-world cash flow needs without off-system tracking.

### Outstanding balance tracking
Each advance maintains remaining balance and settlement status. This gives a clear picture of what is still recoverable.

### Automated settlement during payroll
Advances are automatically adjusted during salary processing using FIFO rules. This removes manual deduction errors and builds worker trust.

---

## 📄 Billing Module

### Bill upload with document attachment
Managers can upload bills and attach PDFs for reference. This improves traceability and simplifies future verification.

### Paid and unpaid status workflow
Bills can be toggled between paid and unpaid states with date behavior. This helps keep vendor obligations visible and current.

### Billing analytics cards
The billing dashboard shows monthly counts, taxable amount, GST amount, and totals. This gives quick visibility into payable obligations and tax impact.

### Billing document retrieval
Uploaded bill files can be opened directly from the dashboard. This saves time during reviews and approvals.

---

## 📊 Expenses Module

### Daily expense entry
Managers can log category-based expenses with payment mode and notes. This keeps small daily spending from being lost or delayed.

### Category-level breakdowns
Expenses are grouped for quick daily and periodic analysis. This helps identify high-spend areas and tighten field controls.

### 7-day edit lock
Older expense records are protected by a 7-day edit/delete lock rule. This prevents backdated tampering and improves reporting discipline.

### Expense dashboard KPIs
Daily, weekly, and monthly totals are shown in summary cards. This gives immediate spend awareness for operational decisions.

### CSV and PDF expense exports
Managers can export expense records in both CSV and PDF formats. This supports accounting handover and compliance documentation.

---

## 🧾 Analytics Module (Audit and Activity)

### Full activity audit logs
Key actions across attendance, payroll, expenses, billing, employee changes, exports, and auth events are logged. This creates a reliable operational history.

### Manager audit view
Managers can review a filtered audit stream relevant to operational monitoring. This helps in internal checks without overwhelming noise.

### Owner audit view
Owner-level audit visibility includes a wider scope for governance and escalation review. This supports top-level control and accountability.

### Audit exports (CSV and PDF)
Audit trails can be exported for reporting, investigation, or external review. This is valuable during disputes, audits, and internal reviews.

---

## 👑 King Module (Owner Control Center)

### Owner financial dashboard
The owner dashboard combines revenue, liabilities, workforce, payroll impact, and activity snapshots. This provides strategic clarity in one place.

### Work order management
Work orders can be created, tracked, and updated through lifecycle statuses. This connects project commitments with financial performance.

### Revenue capture
Manual revenue entries can be recorded against business context. This ensures incoming cash visibility beyond payroll data.

### Ledger management
A running ledger with debit/credit entries and date filtering supports owner-level bookkeeping discipline. This improves financial control and traceability.

### Ledger PDF export
Date-range ledger exports are available in PDF format. This is useful for client meetings, internal finance review, and documentation.

---

## 🛡️ Security and Reliability

### CSRF protection
All sensitive form actions are protected to block unauthorized request forgery. This keeps critical operations safer in browser environments.

### IDOR protection for worker data
Workers are limited to their own salary and payslip records. This prevents unauthorized access to other employee information.

### Role-based access control
Manager, worker, and owner actions are separated by explicit permission checks. This protects business data and reduces accidental misuse.

### Atomic payroll transactions
Payroll and deduction-sensitive operations are executed in transaction-safe flows. This prevents partial updates and keeps financial records consistent.

### Audit trail coverage
System activity is logged with user context and timing. This supports accountability, dispute resolution, and governance.

### Session safety controls
Owner access uses stronger session controls and scoped checks to protect high-privilege areas. This reduces risk around sensitive owner actions.

---

## 📤 Data Export Summary

### Payroll
- CSV salary register export by month for accounting and reconciliation.
- PDF payslip export/download for individual salary proof.

### Expenses
- CSV daily expense export for spreadsheet workflows.
- PDF daily expense report for formal sharing and records.

### Billing
- Bill document retrieval through uploaded PDF files.

### Analytics (Audit)
- CSV export for machine-readable compliance and investigation workflows.
- PDF export for presentation-ready review trails.

### King Ledger
- PDF ledger export by date range for owner-level finance documentation.

---

## 🗺️ Future Roadmap

- Configurable leave policies so paid leave behavior can be tuned per contractor.
- Enhanced payroll correction workflow for controlled post-generation adjustments.
- Deeper statutory reporting packs for PF/ESIC and compliance filing readiness.
- Mobile-first field operations improvements for attendance and expense capture.
- Expanded API integrations for accounting tools and enterprise reporting.
- Advanced notification engine for payment due, liability alerts, and approval events.

---

CWMS delivers practical contractor value by combining workforce operations, payment accuracy, and financial visibility in one dependable system.
