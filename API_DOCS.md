# CWMS Routing and Endpoint Reference

This project is a Django template-rendered monolith. Endpoints below are route-level references (not REST API contracts).

## Conventions
- Method column reflects code behavior and decorators (for example `require_POST`).
- Access control reflects decorators and in-view checks.
- Most endpoints return HTML redirects/pages; JSON endpoints are explicitly marked.

## 1) Root Routing Map
- `/admin/` -> Django admin site
- `/payroll/` -> `payroll.urls`
- `/portal/` -> `portal.urls`
- `/` -> `billing.urls`, `expenses.urls`, `employees.urls`, `analytics.urls`
- `/king/` -> `king.urls`

## 2) Portal Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET, POST | `/portal/login/` | `portal_login` | Public | HTML page/redirect |
| GET | `/portal/dashboard/` | `worker_dashboard` | `worker_required` | HTML page |
| GET | `/portal/logout/` | `worker_logout` | Session user if present | Redirect |
| GET | `/portal/profile/` | `worker_profile` | `worker_required` | HTML page |
| GET | `/portal/attendance/` | `worker_attendance` | `worker_required` | HTML page |
| GET | `/portal/download-payslip/<salary_id>/` | `download_payslip` | `worker_required` + ownership/status checks | PDF |
| GET | `/portal/manager/dashboard/` | `manager_dashboard` | `manager_required` | HTML page |
| GET | `/portal/manager/dashboard/recent-activity/` | `manager_recent_activity_api` | `manager_required` | JSON |
| GET, POST | `/portal/manager/attendance/bulk/` | `bulk_attendance` | `manager_required` | HTML page/redirect |
| GET, POST | `/portal/manager/run-payroll/` | `run_payroll` | `manager_required` | HTML page/redirect |
| GET, POST | `/portal/manager/advances/issue/` | `issue_advance_view` | `login_required` + `manager_required` | HTML page |

## 3) Payroll Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET | `/payroll/payslip/<salary_id>/` | `download_payslip` | `login_required` + in-view permission checks | PDF |
| GET | `/payroll/summary/` | `payroll_batch_summary` | `manager_required` | HTML page |
| GET | `/payroll/manager/payroll/salaries/` | `salary_list_view` | `manager_required` | HTML page |
| POST | `/payroll/manager/payroll/salaries/generate/` | `generate_employee_salary` | `manager_required` + `require_POST` | Redirect |
| POST | `/payroll/manager/payroll/salaries/mark-paid/` | `mark_salary_paid` | `manager_required` + `require_POST` | Redirect |
| GET | `/payroll/manager/payroll/salaries/export/` | `export_salary_list_csv` | `manager_required` | CSV |

## 4) Billing Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET, POST | `/manager/billing/` | `billing_dashboard` | `manager_required` | HTML page/redirect |
| POST | `/toggle_bill_status/<bill_id>/` | `toggle_bill_status` | `manager_required` + `require_POST` | Redirect |
| POST | `/delete_bill/<bill_id>/` | `delete_bill` | `manager_required` + `require_POST` | Redirect |

## 5) Expenses Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET, POST | `/manager/expenses/` | `expense_dashboard` | `manager_required` | HTML page/redirect |
| POST | `/manager/expenses/delete/<expense_id>/` | `delete_expense` | `manager_required` + `require_POST` | Redirect |
| GET, POST | `/manager/expenses/edit/<expense_id>/` | `edit_expense` | `manager_required` | HTML page/redirect |
| GET | `/manager/expenses/export/` | `export_expenses_csv` | `manager_required` | CSV |
| GET | `/manager/expenses/pdf/` | `daily_expense_pdf` | `manager_required` | PDF |

## 6) Employees Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET, POST | `/manager/employees/add/` | `add_employee_view` | `login_required` + `manager_required` | HTML page |
| GET, POST | `/manager/employees/edit/<employee_id>/` | `edit_employee_view` | `login_required` + `manager_required` | HTML page |
| GET | `/manager/employees/` | `employee_list_view` | `login_required` + `manager_required` | HTML page |

## 7) Analytics (Audit) Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET | `/king/audit/` | `king_audit_history` | `king_required` | HTML page |
| GET | `/king/audit/export/csv/` | `king_audit_export_csv` | `king_required` | CSV |
| GET | `/king/audit/export/pdf/` | `king_audit_export_pdf` | `king_required` | PDF |
| GET | `/portal/manager/audit/` | `manager_audit_history` | `manager_required` | HTML page |
| GET | `/portal/manager/audit/export/csv/` | `manager_audit_export_csv` | `manager_required` | CSV |
| GET | `/portal/manager/audit/export/pdf/` | `manager_audit_export_pdf` | `manager_required` | PDF |

## 8) King Endpoints

| Method | Path | View | Access | Response |
|---|---|---|---|---|
| GET, POST | `/king/secure/owner-x7k2/` | `king_login` | Public | HTML page/redirect |
| GET | `/king/dashboard/` | `king_dashboard` | `king_required` | HTML page |
| GET | `/king/dashboard/recent-activity/` | `king_recent_activity_api` | `king_required` | JSON |
| GET | `/king/logout/` | `king_logout` | `king_required` | Redirect |
| GET | `/king/workorders/` | `workorder_dashboard` | `king_required` | HTML page |
| GET, POST | `/king/workorders/add/` | `workorder_add` | `king_required` | HTML page/redirect |
| GET | `/king/workorders/<wo_id>/` | `workorder_detail` | `king_required` | HTML page |
| GET, POST | `/king/workorders/<wo_id>/edit/` | `workorder_edit` | `king_required` | HTML page/redirect |
| POST | `/king/workorders/<wo_id>/status/` | `workorder_status_update` | `king_required` + `require_POST` | Redirect |
| GET | `/king/revenue/` | `revenue_dashboard` | `king_required` | HTML page |
| POST | `/king/revenue/add/` | `revenue_add` | `king_required` + `require_POST` | Redirect |
| POST | `/king/revenue/delete/<rev_id>/` | `revenue_delete` | `king_required` + `require_POST` | Redirect |
| GET | `/king/ledger/` | `ledger_view` | `king_required` | HTML page |
| POST | `/king/ledger/add/` | `ledger_add_entry` | `king_required` + `require_POST` | Redirect |
| POST | `/king/ledger/delete/<entry_id>/` | `ledger_delete_entry` | `king_required` + `require_POST` | Redirect |
| GET | `/king/ledger/pdf/` | `ledger_pdf` | `king_required` | PDF |

## 9) Authorization Summary
- `worker_required`: worker-only access on worker pages.
- `manager_required`: manager access; includes owner read-only viewing mode in some manager surfaces.
- `king_required`: strict owner gate requiring authenticated user, session flag, and King group membership.

## 10) Notes
- This codebase is server-rendered Django (templates + redirects), not DRF/GraphQL.
- Export endpoints are primarily CSV/PDF and generally use GET.
- Mutating operations in billing/expenses/payroll/king critical actions are POST-hardened.
