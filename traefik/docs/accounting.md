# Accounting

Two addons: **`custom_accounting_basic`** (M5 — invoicing, bank import, reconciliation) and
**`custom_accounting_advanced`** (M11 — full ledger, reports, period locks, BV annual
accounts). Both extend Odoo's native accounting rather than replacing it, so the standard
`account.move` / `account.move.line` engine and its debit=credit invariants apply.

## custom_accounting_basic (M5)

**Outgoing invoices** — generate from quote/order/time/rental; recurring
(`recurring.invoice.template` + lines, `action_create_now`); partial and pro forma
(`action_send_proforma` / `action_remove_proforma`); payment-link placeholder (Mollie);
reminders (`action_send_payment_reminder`); status tracking. Post with `action_post`.

**Incoming invoices** — upload PDF/image → OCR/AI extraction (supplier, number, dates,
amounts, VAT, IBAN, reference, line items) via `action_ai_extract_review` → duplicate
detection (`action_detect_duplicates`) → approval → journal proposal → payment link.
OCR provider defaults to `mock`; set `OCR_PROVIDER`/`MINDEE_API_KEY`/`AZURE_DOCAI_*` to
upgrade accuracy. Without a key it degrades to manual entry.

**Bank import & matching** — parse CSV / MT940 / CAMT.053 (file import always works,
no key). Matching keys on invoice number / IBAN / amount / party. AI-suggested matches
carry a confidence score (`action_suggest_ai_match` → `action_confirm_ai_match`).
Handles split / partial / over / under-payment and an unknown-payment queue.

**Audit** — `accounting.audit.log` records events; corrections trace cleanly from
invoice → journal → payment.

### Bank import entry point
Statements can also arrive via the integration gateway: `POST /webhooks/bank/import`
(secured by `BANK_IMPORT_SECRET`), which normalises and forwards into Odoo. See
`tests/fixtures/data/camt053_sample.xml` for a minimal valid CAMT.053 used by the tests.

## custom_accounting_advanced (M11)

**Ledger** — chart of accounts, journals, journal entries, fiscal years, periods,
**period locks**, opening balance, closing entries.

**Reports** — balance sheet, P&L, trial balance, general ledger, aged receivables/payables,
VAT summary, cash-flow, cost centers, departments, projects, fixed assets + depreciation,
accruals/prepayments/provisions, audit-file export, management reports, period comparison,
budget-vs-actual.

**BV annual accounts** — company type, draft package (balance sheet, P&L, notes template,
management-report placeholder, equity overview, retained-earnings calc), PDF/Word export,
and an accountant review workflow with a dedicated accountant access role.

**Controls** — immutable audit metadata on entries; corrections only via reversal (no
in-place edits); period lock prevents posting/edits; admin override requires a reason and
is audited; attachments per entry; full tax-audit export.

## Invariants worth knowing

- Posted moves satisfy `sum(debit) == sum(credit)`; the e2e suite asserts this
  (`tests/e2e/test_sales_to_cash.py`).
- A locked period rejects new postings in that range.
- Reversal is the only correction path on posted entries.

## Keys

Nothing here requires a key to function. Optional upgrades: `MINDEE_API_KEY` /
`AZURE_DOCAI_*` (OCR accuracy), `MOLLIE_API_KEY` / `STRIPE_API_KEY` (pay-by-link),
`GOCARDLESS_BANKDATA_*` (live PSD2 feed instead of file import).
