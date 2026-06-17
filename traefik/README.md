# Platform — Modular CRM/ERP on Odoo 19

A production-grade, modular, multi-tenant business platform built on **Odoo 19 Community**.
Branded, extensible, and licensable per-module to clients.

## Quick start (dev — native)

```bash
# First time
make install-dev   # install ruff, black, pre-commit
make init          # create DB + install Odoo base (~2 min)

# Daily
make up            # start server → http://localhost:8070
make down          # stop server
make logs          # tail log
make shell         # Odoo Python REPL
```

## Modules

| Module | Description |
|---|---|
| `custom_theme` | Branded backend, portal, company branding |
| `custom_subscription_modules` | Module licensing, feature flags, trial mode |
| `custom_ai_core` | LLM provider abstraction, RAG, prompt store |
| `custom_crm_core` | Extended CRM with AI scoring, GDPR |
| `custom_quote_signing` | Quote lifecycle + electronic signing |
| `custom_accounting_basic` | Invoicing, bank import, reconciliation |
| `custom_planning` | Appointments, jobs, calendar |
| `custom_inventory` | Stock, warehouses, purchase orders |
| `custom_rental` | Rental workflow, pricing tiers |
| `custom_hrm` | Employee DB, leave, sick-leave |
| `custom_payroll_nl` | Dutch payroll, payslips, export |
| `custom_accounting_advanced` | CoA, reports, BV annual accounts |
| `custom_ai_chatbot` | Website chat, RAG, escalation |
| `custom_helpdesk` | Tickets, SLA, AI drafts |
| `custom_email_ai` | Mailbox, AI classification, pending outbox |
| `custom_whatsapp_social` | WhatsApp, social inbox, post planning |
| `custom_ai_voice` | VoIP, STT, TTS, call transcription |

## Stack

- **Odoo 19 Community** — `/home/diviner/Odoo/19/`
- **PostgreSQL 16** — database
- **Python 3.12** — runtime
- **Port 8070** — dev server (8069 is reserved for other projects)

## Env vars

Copy `.env.example` → `.env`. All keys are optional — core platform runs without any.

## Dev tools

```bash
make lint        # ruff + black --check
make format      # ruff --fix + black
make test        # run addon test suite
make check       # full pre-commit pass
```

## Docs

See [`docs/`](docs/) for architecture, installation, modules, API keys, and devlog.
