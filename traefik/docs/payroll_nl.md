# Dutch payroll (`custom_payroll_nl`, M10)

Implements the **data model, calculations, payslips, journal entries, reports, and
export/integration interface** for Netherlands payroll. It deliberately stops short of
live official filing — see "Legal blocker" below.

## Models

| Model | Role |
|---|---|
| `hr.payroll.run` | a payroll period (monthly / 4-week); orchestrates the run |
| `hr.payroll.payslip` | per-employee slip with gross→net breakdown and YTD |
| `hr.payroll.rule.version` | **versioned** yearly tax/contribution parameters |
| `hr.payroll.override` | manual override of a computed field, with reason |
| `hr.payroll.access.log` | immutable audit of every payroll-data access |

## Run lifecycle (`hr.payroll.run`)

`action_calculate` → `action_confirm` → `action_approve` → `action_publish_payslips`
(secure publication to the employee portal) → `action_post_journal` (creates the payroll
journal entry). Exports: `action_export_accountant`, `action_export_payroll_provider`,
`action_export_annual_statement`.

Per-slip: `action_calculate`, `action_publish`, and `action_apply_override(field_name,
new_value, reason)` which records an `hr.payroll.override` and audits it.

## Salary components

Employer settings, payroll-tax-number, period config, employee payroll profile, tax data,
**loonheffingskorting** (wage-tax credit) toggle, gross/hourly wage, contract hours,
overtime, allowances, expense reimbursements, deductions, pension fields,
**vakantiegeld** (holiday allowance), bonus, sick-pay placeholder, company-car placeholder,
travel allowance. The payslip PDF shows gross components, deductions, employer
contributions, net, accrued holiday allowance, period, and YTD.

## Versioned rules engine

No hardcoded tax tables. Parameters live in `hr.payroll.rule.version`, keyed by year and
version (`display_name` = `NL Payroll Rules {year} v{version}`). Each calculation stores its
explanation; manual overrides require a reason; the engine warns when parameters are
missing or outdated. Updating for a new tax year is adding a new version record, not a code
change.

## Security

Payroll data is visible only to Payroll/HR roles; an employee sees only their own slips
(portal `/my/payslips`, scoped). **Every access is written to `hr.payroll.access.log`.**
Payroll content defaults to local AI / no external provider.

## Legal blocker — do not fake

Direct official filing to the Belastingdienst (**loonaangifte**) requires a **certified
route**. This addon implements everything up to and including export/integration, and marks
filing as **"prepared for filing / export / external submission."** Connecting a certified
provider (and its credentials) is an external step that must be requested before any claim
of live submission. This is also recorded in `docs/devlog.md`.

## Tests

`addons/custom_payroll_nl/tests` covers gross→net, holiday-allowance accrual, employer
costs, override-with-reason audit, and role isolation. The cross-service smoke flow is in
`tests/e2e/test_payroll_flow.py`.
