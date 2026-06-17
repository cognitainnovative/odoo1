# Security Architecture

## RBAC Groups

| Group | Access |
|---|---|
| `base.group_system` | Super admin — all models, all companies |
| `base.group_user` | Standard internal user |
| `base.group_public` | Unauthenticated portal/webhook access (minimal) |
| `account.group_account_manager` | Accounting manager — fiscal years, advanced reports |
| `account.group_account_invoice` | Accountant — invoices, bank, budgets |
| `hr.group_hr_manager` | HR manager — employees, payroll, sick leave |
| `hr.group_hr_user` | HR officer — leave requests, sick leave view |
| `sales_team.group_sale_manager` | Sales manager — campaigns, discount tier approval |
| `sales_team.group_sale_salesman` | Sales user — CRM, rental, quotes |

## Company Isolation

All custom models with `company_id` have record rules restricting read/write to `company_ids`. Portal users see only their own data via email/partner matching.

## API Key Encryption

Provider API keys (AI, WhatsApp, VoIP) are encrypted at rest using Fernet symmetric encryption. The encryption key is loaded from `APP_SECRET_ENCRYPTION_KEY` env var. A dev fallback key is hardcoded — **replace in production**.

## Audit Logs (Immutable)

| Model | Immutability |
|---|---|
| `ai.audit.log` | `write()`/`unlink()` always raise `UserError` |
| `quote.signing` | `write()`/`unlink()` always raise `UserError` |
| `hr.payroll.override` | `write()` raises `UserError` |
| `chat.transcript.line` | read-only after creation |
| `voice.transcript.line` | read-only after creation |

## Payroll Security

- Payroll data scoped to `hr.group_hr_manager` only
- Record rules: payslips visible to own employee + HR managers
- YTD totals only updated by the payroll run process
- **Content never sent to external AI** by default (local/mock only)

## Signing Audit Evidence

Each `quote.signing` record captures: signer name+email, timestamp, IP, user-agent, document SHA-256 hash, document version, terms version, terms+payment acceptance flags, event log. All immutable.

## GDPR

- Contact data export: `res.partner.action_export_gdpr_data()`
- Lead anonymization: `crm.lead.action_anonymize()`
- Sick leave: stores ONLY admin data — no diagnoses, no medical content
- Verification records: BSN last-4-only, no full document numbers

## Legal Blockers (Document, Not Fake)

- Dutch loonaangifte: data prepared, NOT filed
- eIDAS qualified signatures: simple/advanced only
- Meta WhatsApp: sandbox until Business App Review approved
- X/Twitter: mock until paid API tier activated
- Call recording: consent-gated, two-party flag per jurisdiction
