# Claude Code — Build Brief
## Modular CRM / ERP / Accounting / HRM / Payroll / Inventory / Rental / AI Platform on Odoo Community

> **Read this entire file before writing any code.** It is the single source of truth for the build.
> Keep it open. Update the **Development Log** section (or `docs/devlog.md`) after every milestone.

---

## 0. Your role and operating contract

You are **Claude Code**, acting simultaneously as: senior full-stack engineer, Odoo architect, ERP/CRM solution architect, security engineer, AI systems engineer, DevOps engineer and QA lead.

You will build a **production-grade, modular, multi-tenant business platform** on top of the latest stable free/open-source **Odoo Community** edition. The result must become *our own commercial product* — branded, extended, secure, modular, and sellable per-module to clients. It must **not** feel like a raw Odoo install.

### Operating rules (non-negotiable)

1. **Work autonomously.** Implement the project as far as technically possible. Do not stop at a skeleton.
2. **Work in milestones.** Start with the foundation and implement in the milestone order below. **After each milestone: run tests, fix errors, commit the code, then continue automatically to the next milestone.** Do **not** pause for confirmation between milestones.
3. **Only stop and ask** when genuinely blocked by one of:
   - **Missing credentials** (an API key/secret that has no graceful-degradation path and is required to proceed),
   - **Legal certification requirements** (e.g. certified Dutch wage-tax filing, eIDAS qualified signatures),
   - **External API approval** (e.g. WhatsApp Business / Meta app review, X API access tier).
   For everything else: **choose the best maintainable default, document the assumption in the devlog, and continue.**
4. **Never edit Odoo core.** Build namespaced custom addons. If a core change seems unavoidable, isolate it in a documented `patches/` layer and explain why.
5. **Upgrade-safe.** Target Odoo 19 Community if stable in the environment; otherwise Odoo 18 Community, structured for a clean upgrade to 19+.
6. **Avoid Enterprise-only dependencies and vendor lock-in.** Prefer Odoo-native strengths; build custom where Community lacks features.
7. **Security and auditability first.** Every financial, payroll, signing, and AI action is logged and traceable.
8. **Features degrade gracefully** when optional API keys are absent. The system must always boot and run core CRM with zero third-party keys.
9. **Commit discipline:** small, conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). Tag the end of each milestone (`m0-foundation`, `m1-crm`, …).
10. **Quality gates:** linting (`ruff`, `black`, `pylint-odoo`), tests, and a green CI run are required before a milestone is considered done.

### Decision rule when a choice is needed
Choose the option that is, in priority order: (1) most maintainable, (2) Odoo-native if Odoo is strong there, (3) custom module if Community is missing it, (4) free/open-source over paid, (5) upgrade-safe, (6) most secure/auditable, (7) shippable now over theoretically perfect.

---

## 1. Recommended technology stack (final choices)

These are **decided defaults** — implement them unless the environment makes one impossible, in which case document the substitution.

| Layer | Choice | Rationale |
|---|---|---|
| ERP core | **Odoo 19 Community** (fallback 18) | Free, modular, strong ORM, native accounting/CRM/inventory/HR. |
| Language | **Python 3.11+** | Odoo runtime. |
| DB | **PostgreSQL 16** | Odoo requirement; hosts pgvector too. |
| Vector store | **pgvector** (extension on the same Postgres) | No extra infra, tenant isolation via rows, transactional with business data. Only move to a dedicated store (Qdrant) if scale demands it. |
| Cache / queue / realtime | **Redis 7** | Sessions, rate limits, pub/sub for chat/voice, Celery broker. |
| Background jobs | **Celery** (+ Redis broker, beat for cron) | Mature, observable, retries. |
| External AI/integration service | **FastAPI** microservice (`services/ai_gateway`, `services/integration_gateway`) | Async-friendly for streaming LLM, webhooks, long calls that don't belong in Odoo workers. |
| Object storage | **MinIO** (dev) / **Cloudflare R2** or S3 (prod) | S3-compatible; R2 has zero egress fees. |
| Employee support app | **React + Vite + TypeScript + Tailwind** (`services/support_app`) | Real-time chat/voice console is cleaner outside Odoo views. Talks to FastAPI + Odoo JSON-RPC. |
| Reverse proxy | **Traefik** | Auto-TLS (Let's Encrypt), label-based routing, fits Docker/K8s. |
| Containerization | **Docker Compose** (dev) + **Kubernetes manifests/Helm** (prod-ready, `deploy/k8s`) | Reproducible local + path to prod. |
| CI/CD | **GitHub Actions** | Lint, test, build images, security scan. |
| Error monitoring | **Sentry** (self-hostable) | Backend + frontend exceptions. |
| Metrics/logs | **Prometheus + Grafana + Loki** (optional profile) | Observability; keep behind a compose profile so it's opt-in. |
| Secrets (prod) | **SOPS + age** or **Doppler** | `.env` for dev only; never commit real secrets. |
| Lint/format/test | `ruff`, `black`, `pylint-odoo`, `pytest`, Odoo test framework, `pre-commit` | Consistent quality gates. |

---

## 2. API keys & external services — recommendations + what is actually required

**Principle:** the platform boots and runs core CRM, quoting, invoicing, inventory, rental, HRM, planning and helpdesk **with no external keys at all** (using mocked/local fallbacks). External keys unlock the AI/communication/payment features. Document each in `.env.example` and `docs/api_keys.md` with: what it unlocks, free tier, and the graceful-degradation behaviour when absent.

### 2.1 AI / LLM (pick the best per task — multi-provider abstraction is mandatory)

| Purpose | Recommended primary | Why / cost note | Fallback |
|---|---|---|---|
| Complex drafting (customer-facing email, legal/financial replies, social posts, call summaries) | **Anthropic Claude** (`claude-opus`/`claude-sonnet` class) | Best quality + safety for customer/legal text. `ANTHROPIC_API_KEY`. | OpenAI `gpt-4o`/`gpt-5` class |
| Cheap/fast classification, routing, sentiment, short summaries | **Low-cost fast model** (Claude Haiku class or `gpt-4o-mini` class) | High volume, low cost. | Local Ollama model |
| Embeddings (RAG) | **Local via Ollama** (`nomic-embed-text` / `bge-m3`) by default; **OpenAI `text-embedding-3-small`** if no GPU | Local keeps data in-house (privacy default) and is free; OpenAI is cheap and good. | Either direction |
| Fully local / privacy mode | **Ollama** (`OLLAMA_BASE_URL`) | Zero data egress for sensitive tenants; **mandatory** path for payroll/financial data. | — |
| Azure-hosted enterprise tenants | **Azure OpenAI** (placeholder wired) | Some clients require Azure data residency. | — |

> **Hard rule:** payroll and financial-record content is **never** sent to an external provider unless the company explicitly enables it in settings. Default = local/redacted only.

### 2.2 Document OCR / invoice extraction

| Recommended | Note |
|---|---|
| **Default (free, no key):** Tesseract OCR + `pdfplumber`/`pypdf` for text, then a **vision-capable LLM** (Claude/GPT-4o vision) for structured field extraction. | Works offline-ish; LLM step needs an AI key but degrades to manual entry without one. |
| **Optional cloud upgrade:** **Mindee** (invoice-specialized) or **Azure Document Intelligence** | Higher accuracy on messy invoices. Keys: `MINDEE_API_KEY` / `AZURE_DOCAI_*`. Optional. |

### 2.3 WhatsApp

| Recommended | Note |
|---|---|
| **Meta WhatsApp Cloud API** (official) — primary | Lowest per-message cost at scale; **requires Meta Business app review** (this is a valid "stop and ask/approval" blocker). Keys: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`. |
| **Twilio WhatsApp** or **360dialog** — easiest start / fallback | Faster to sandbox-test. Abstract behind `WHATSAPP_PROVIDER`. |

### 2.4 SMS — **Twilio** (`TWILIO_*`) primary, **MessageBird** fallback. Abstracted.

### 2.5 VoIP + AI voice agent

| Component | Recommended | Note |
|---|---|---|
| Telephony | **Twilio Voice** (`TWILIO_*`) primary; self-host **Asterisk**/3CX via SIP webhook abstraction as the lock-in-free option | Twilio is fastest; SIP abstraction keeps options open. |
| Speech-to-text (real-time) | **Deepgram** (`DEEPGRAM_API_KEY`) | Best latency/price for live calls. |
| Speech-to-text (batch transcription) | **OpenAI Whisper** (self-hosted, free) | No key; runs locally for recorded-call transcription. |
| Text-to-speech | **ElevenLabs** (`ELEVENLABS_API_KEY`) primary; OpenAI TTS / Azure fallback | Most natural voices. |
| Realtime alternative | **OpenAI Realtime API** | Single-vendor low-latency voice loop if preferred. |

### 2.6 Email

| Recommended | Note |
|---|---|
| **Generic IMAP/SMTP** (always available) + **Microsoft 365 Graph** (`MICROSOFT_*`) + optional **Gmail API** | Graph for O365 tenants; IMAP/SMTP universal fallback. |
| Transactional/outbound deliverability: native SMTP, or **Postmark**/**SendGrid** (optional) | Better inbox placement for invoices/quotes. |

### 2.7 Bank / PSD2

| Recommended | Note |
|---|---|
| **File import first:** CAMT.053, MT940, CSV (no key, always works) | Definition-of-done baseline. |
| **Optional live feed:** **GoCardless Bank Account Data** (formerly Nordigen) | **Free** PSD2 EU bank connections — best value. `GOCARDLESS_BANKDATA_*`. Tink/Plaid as alternatives. |

### 2.8 Payments (value-add)

| Recommended | Note |
|---|---|
| **Mollie** (`MOLLIE_API_KEY`) primary for the NL/EU market; **Stripe** fallback | Generate pay-by-link on invoices/quotes; iDEAL support is essential for Dutch clients. |

### 2.9 Social media — **Meta Graph** (FB/IG, `META_*`), **LinkedIn** (`LINKEDIN_*`), **X/Twitter** (`X_*`, note paid tiers + approval). All optional, publishing degrades to "draft + manual copy" without keys.

### 2.10 Object storage — `S3_ENDPOINT/S3_ACCESS_KEY/S3_SECRET_KEY/S3_BUCKET` (MinIO locally, no external account needed).

### 2.11 Monitoring (value-add) — **Sentry** (`SENTRY_DSN`, optional).

> Full placeholder list lives in `.env.example` (Section 11). **Do not require any key to run locally.**

---

## 3. High-level architecture

```
                         ┌─────────────────────────────────────────────┐
                         │                 Traefik (TLS)               │
                         └───────┬───────────────┬───────────────┬─────┘
                                 │               │               │
                        ┌────────▼──────┐ ┌──────▼───────┐ ┌─────▼────────┐
                        │  Odoo Community│ │ FastAPI:     │ │ React support│
                        │  + custom_*    │ │ ai_gateway   │ │ app (Vite)   │
                        │  addons        │ │ integration_ │ │              │
                        │  (web + portal)│ │ gateway      │ │              │
                        └───┬───────┬────┘ └──┬────────┬──┘ └──────┬───────┘
                            │       │         │        │           │
                ┌───────────▼─┐ ┌───▼────┐ ┌──▼───┐ ┌──▼─────┐ ┌───▼─────┐
                │ PostgreSQL  │ │ Redis  │ │Celery│ │ MinIO/ │ │ Webhooks│
                │ + pgvector  │ │        │ │worker│ │  S3    │ │(WA/Voice│
                └─────────────┘ └────────┘ │+beat │ └────────┘ │ /social)│
                                           └──────┘            └─────────┘
```

- **Odoo** owns business data, ORM, ACLs, record rules, accounting/HR/inventory engines, portal, and most UI.
- **ai_gateway** (FastAPI): provider abstraction, RAG pipeline, redaction, streaming chat, prompt store, AI audit. Odoo calls it over an internal authenticated channel; it never holds business data of record, only transient context.
- **integration_gateway** (FastAPI): inbound webhooks (WhatsApp, voice, social, bank, signing callbacks), normalizes and pushes into Odoo via JSON-RPC / message queue.
- **support_app** (React): live chat/voice agent console for employees; auth via Odoo session + scoped token.
- **Celery**: OCR, embeddings indexing, payroll runs, scheduled posts, reminders, reconciliation suggestions.

**Multi-tenant / multi-company:** use Odoo `res.company` multi-company + record rules for soft multi-tenant within one instance; document the per-instance (database-per-tenant) deployment path for hard isolation. Module licensing (Milestone 14) gates feature/menu access per company.

---

## 4. Repository structure (create/initialize)

```
/
├─ docker-compose.yml
├─ docker-compose.override.yml          # dev conveniences
├─ docker-compose.monitoring.yml        # optional profile: Sentry/Prometheus/Grafana/Loki
├─ .env.example
├─ .gitignore
├─ .pre-commit-config.yaml
├─ Makefile
├─ README.md
├─ pyproject.toml                       # ruff/black config
├─ .github/workflows/ci.yml
├─ docs/
│  ├─ architecture.md  installation.md  modules.md  deployment.md
│  ├─ security.md  accounting.md  payroll_nl.md  ai.md  testing.md
│  ├─ api_keys.md  onboarding_client.md  upgrade_notes.md  devlog.md
├─ scripts/
│  ├─ init.sh  backup.sh  restore.sh  run_tests.sh  create_demo_data.sh  seed_data.sh
├─ config/
│  └─ odoo.conf
├─ addons/
│  ├─ custom_theme/
│  ├─ custom_subscription_modules/
│  ├─ custom_ai_core/
│  ├─ custom_crm_core/
│  ├─ custom_quote_signing/
│  ├─ custom_accounting_basic/
│  ├─ custom_accounting_advanced/
│  ├─ custom_hrm/
│  ├─ custom_payroll_nl/
│  ├─ custom_inventory/
│  ├─ custom_rental/
│  ├─ custom_ai_chatbot/
│  ├─ custom_ai_voice/
│  ├─ custom_helpdesk/
│  ├─ custom_email_ai/
│  ├─ custom_whatsapp_social/
│  └─ custom_planning/
├─ services/
│  ├─ ai_gateway/        # FastAPI, RAG, provider abstraction, redaction
│  ├─ integration_gateway/  # webhooks normalizer
│  └─ support_app/       # React/Vite/TS
├─ deploy/
│  └─ k8s/               # manifests / Helm chart
└─ tests/
   ├─ e2e/  api/  fixtures/
```

Each Odoo addon follows the standard layout: `__manifest__.py`, `models/`, `views/`, `security/` (`ir.model.access.csv` + `record_rules.xml`), `data/`, `wizards/`, `controllers/`, `report/`, `static/`, `tests/`, `i18n/`, `README.md`.

---

## 5. Milestones (execute in order, test→fix→commit→continue)

> Each milestone lists **Deliverables**, **Acceptance criteria**, and a **Test gate**. A milestone is "done" only when its test gate is green and the code is committed and tagged.

### M0 — Foundation & environment  `tag: m0-foundation`
**Deliverables:** repo init; `docker-compose.yml` (Odoo, Postgres+pgvector, Redis, MinIO, Traefik, ai_gateway, integration_gateway placeholders); `config/odoo.conf` (dev mode, custom addons path); `.env.example`; `Makefile` (`up`, `down`, `logs`, `shell`, `test`, `lint`, `backup`, `restore`, `init`, `seed`); `scripts/*`; `pre-commit`; `.github/workflows/ci.yml`; base `docs/` skeleton; `docs/devlog.md`.
**Acceptance:** `make up` brings Odoo online; pgvector extension enabled; MinIO bucket auto-created; CI runs lint+empty test suite green.
**Test gate:** `scripts/run_tests.sh` passes (bootstrap test that asserts DB connectivity, pgvector present, Redis reachable, MinIO reachable).

### M1 — `custom_theme` (functional first, polish later) + `custom_subscription_modules`  `tag: m1-foundation-modules`
**Deliverables:**
- **custom_theme:** branded backend (configurable logo, favicon, calm business palette, typography), improved menu grouping, base dashboard shell with cards, responsive portal styling. Branding stored in company settings (logo, colors, email/PDF/portal templates).
- **custom_subscription_modules:** module/package registry, per-company subscription records, feature flags, trial mode, renewal/billing status, usage limits, license-key placeholder, menu/route gating for inactive modules, graceful data retention when a module is disabled, admin dashboard. Packages defined: CRM Base, Finance Basic, Finance Advanced, HRM, Payroll NL, Inventory, Rental, AI Chat, AI Voice, Helpdesk, Social Media, Planning, Full Suite.
**Acceptance:** disabling a module hides its menus/routes but keeps data; branding visibly applied.
**Test gate:** access tests prove inactive-module menus/controllers are blocked; subscription state transitions covered.

### M2 — `custom_ai_core`  `tag: m2-ai-core`
**Deliverables:** provider abstraction (OpenAI-compatible, Anthropic, Azure placeholder, Ollama) with per-company model/key settings, temperature, max tokens, **privacy mode**, **redaction/data-minimization before external calls**, "allow external AI yes/no" toggle; prompt template store with **versioning**, evaluations, outputs; RAG pipeline in `ai_gateway` (ingest PDF/DOCX/TXT/HTML/CSV → chunk → embed → pgvector → search with **source citations + confidence score**); tenant/company isolation of documents and vectors; re-index + delete (with embedding deletion); document permissions; **AI audit log**; user feedback + **correction-learning store** (original draft, edited reply, reason, category, knowledge source, "add to KB?" flag, approval status — used to enrich prompt context, **not** blind fine-tuning); AI task queue (Celery); **mock provider** for tests/CI.
**Acceptance:** with no keys, mock provider answers; with a key, real provider answers; RAG returns cited chunks; redaction strips configured PII before external calls.
**Test gate:** AI prompt tests with mocked providers; RAG retrieval test; redaction test; tenant-isolation test (company A cannot retrieve company B docs).

### M3 — `custom_crm_core`  `tag: m3-crm`
**Deliverables:** Zoho-like CRM extending Odoo CRM — Lead, Contact, Company/account, Deal/opportunity, Activity, Quote, Sales order, Communication history, Notes, Documents, Tasks, Follow-ups, Lead source, Campaign, Pipeline, Stage, Probability, Expected revenue, Close date, Assigned employee, Tags, **custom fields per company**. Features: kanban pipeline, lead capture, lead scoring, **AI lead summary**, duplicate detection, merge contacts, activity reminders, AI follow-up suggestions, per-contact & per-deal timeline, email/call/WhatsApp/chat logging, quote & signed-doc history, **consent/GDPR fields + export/anonymize**, CSV import/export, API endpoints. Dashboards: new leads, open deals, expected revenue, won/lost, conversion rate, overdue follow-ups, lead-source performance, employee performance.
**Test gate:** lead→deal→quote flow unit/integration tests; duplicate detection; GDPR export.

### M4 — `custom_quote_signing`  `tag: m4-signing`
**Deliverables:** quote lifecycle (draft→sent→viewed→accepted-pending→signed→confirmed→invoiced→cancelled→expired); secure customer signing portal showing price clearly, **terms & conditions popup**, **active acceptance checkbox**, **explicit payment-obligation wording** (configurable + translatable, default text per brief, **not hardcoded Dutch**); typed or drawn signature; on sign → store **full audit evidence** (signer name, email, timestamp, IP, user agent, terms version, document version, **document hash**, signature, event log) → generate signed PDF → deal won/confirmed → email signed copy → internal notification → **auto-create planning task** if the product/service needs execution. Templates: quote, line, terms-version, email, signed-PDF.
**Compliance note:** this is a **simple/advanced electronic signature**, not an eIDAS **qualified** signature. If a client needs qualified signatures, that requires a QTSP integration — **flag as external approval/legal blocker** and provide the interface only.
**Test gate:** signing audit test (hash stable, all evidence captured); lifecycle transitions; planning task auto-creation.

### M5 — `custom_accounting_basic`  `tag: m5-acct-basic`
**Deliverables:** extend Odoo invoicing/accounting — outgoing/incoming invoices, credit notes, customers, suppliers, products, tax rates, VAT overview, payment status, payment reminders, invoice PDF/email, **bank import (CSV/MT940/CAMT.053)**, payment matching, manual reconciliation, **AI-suggested reconciliation with confidence score**, debtor/creditor/revenue/expense overviews, Excel/CSV export, audit trail. Incoming-invoice flow: upload PDF/image → OCR/AI extraction (supplier, number, dates, amounts, VAT, IBAN, reference, line items) → duplicate detection → approval → booking/journal proposal → auto payment link. Outgoing: generate from quote/order/time/rental, recurring, partial, pro forma, payment-link placeholder (Mollie), reminders, status. Bank: parse description, match on invoice no./IBAN/amount/party, AI suggestions + confidence, split/partial/over/underpayment, unknown-payment queue.
**Test gate:** bank-matching tests (incl. partial/split); incoming-invoice extraction with mocked AI; accounting consistency (debits=credits).

### M6 — `custom_planning`  `tag: m6-planning`
**Deliverables:** appointment/task/job/slot/resource/team/location objects linked to deal/order/invoice/contact; calendar + kanban board; employee availability & skills; travel/location notes; customer confirmation email; reminders; reschedule workflow; mobile-friendly employee view; completion report; optional customer sign-off. Use cases wired: accepted quote→job, installation/service appointment, rental pickup/return, sales/follow-up call, internal task, HR meeting, support callback.
**Test gate:** quote-accept→planning-task linkage; reschedule + reminder scheduling.

### M7 — `custom_inventory`  `tag: m7-inventory`
**Deliverables:** products/variants, warehouses, locations, serial/lot, supplier, purchase order, stock moves/reservations/counts/adjustments, reorder rules, bundles; on-hand/available/reserved/incoming/outgoing; **auto stock deduction on order/invoice confirm (config: deduct on delivery instead)**; reservation from quote/order; low-stock alerts; supplier order suggestions; images/docs; SKU/barcode; stock valuation; count workflow; audit trail. Dashboards: low stock, fast-movers, stock value, reserved, out-of-stock, warehouse overview.
**Test gate:** confirm-order→stock-decrease; reservation; valuation.

### M8 — `custom_rental`  `tag: m8-rental`
**Deliverables:** rentable product, rental item/stock/order/contract, pricing rules (per day/week/month, custom periods, weekend, minimum period, deposit, insurance, cleaning, damage waiver, late fee, discounts, loyalty), availability calendar, deposit handling, **ID/KVK verification record (status, expiry, risk flag, configurable retention, minimal PII)**, pickup/return records, damage report, late fee, discount reason. Full workflow (quote→availability→reserve→sign→deposit→verify→pickup→stock-out→monitor→reminder→return→inspect→damage→final amount→invoice→deposit release/deduct→back to available). **Customer discount/bonus tiers** (standard/silver/gold/platinum/negotiated) with auto-tier by annual spend, manual override, category/duration/volume/project discounts, **required reason + approval above threshold + audit**. Dashboard: active/overdue/upcoming returns, revenue, utilization, damaged items, best products, customer rental value. Recurring rental billing.
**Test gate:** rental availability test; full rental lifecycle; blocked stock during rental; final invoice incl. damages/late fees.

### M9 — `custom_hrm`  `tag: m9-hrm`
**Deliverables:** employee DB (personal, address, emergency contact, contract, dates, dept, manager, title, hours, salary-data reference, documents, certifications, equipment, notes, roles, portal access); **employee self-service portal** (profile, payslips, leave request, sick report, leave balance, holiday allowance, planning, HR docs, upload, announcements, optional HR-doc signing); leave types (vacation/special/unpaid/sick/parental placeholders) with accrual/carry-over/expiry, manager+HR approval, calendar, notifications; sick-leave flow (report/recovery/partial, **privacy-safe — no unnecessary medical data**, manager/HR notification, absence timeline, reintegration placeholders); HR workflows (onboarding/offboarding checklists, contract-renewal/probation/document-expiry/certification reminders, performance-review planning, equipment-return).
**Test gate:** leave request→approval→balance update; sick report privacy fields; portal payslip visibility scoped to self.

### M10 — `custom_payroll_nl`  `tag: m10-payroll`
**Deliverables:** employer settings, payroll-tax-number field, monthly/4-week period config, employee payroll profile, tax data, **wage-tax-credit (loonheffingskorting)** setting, gross/hourly wage, contract hours, overtime, allowances, expense reimbursements, deductions, pension fields, **holiday allowance (vakantiegeld)**, bonus, sick-pay placeholder, company-car placeholder, travel allowance; payroll run → payslip draft → approval → secure publication to portal; payroll journal entry; wage-cost & employer-cost reports; annual-statement data; **export for accountant + export for payroll provider**; audit trail. **Flexible, versioned rules engine** (no hardcoded tax tables; yearly versioned parameters; per-year updatable; stored calculation explanation; manual override with reason; warnings when parameters missing/outdated). Payslip PDF: gross components, deductions, employer contributions, net, accrued holiday allowance, period, YTD. **Security:** payroll data only for payroll/HR roles; employee sees only own; **all access audited**; payroll content default = local AI/no external.
**Legal blocker (flag, do not fake):** Direct official filing to the Belastingdienst (loonaangifte) requires a **certified route**. Implement the **data model, calculations, payslips, journal entries, reports, and export/integration interface**, and mark filing as **"prepared for filing / export / external submission."** Stop and request the certified-provider connection/credentials before claiming live submission.
**Test gate:** payroll calculation tests with sample data (gross→net, holiday allowance accrual, employer costs); override-with-reason audit; role isolation.

### M11 — `custom_accounting_advanced`  `tag: m11-acct-advanced`
**Deliverables:** chart of accounts, journals, journal entries, fiscal years, periods, **period locks**, opening balance, closing entries; reports — balance sheet, P&L, trial balance, general ledger, aged receivables/payables, VAT summary, cash-flow, cost centers, departments, projects, fixed assets + depreciation schedules, accruals/prepayments/provisions, intercompany (where feasible), **audit-file export**, management reports, period comparison, budget-vs-actual (if feasible). **BV annual-accounts preparation** (company type, draft package, balance sheet, P&L, notes template, management-report placeholder, equity overview, retained-earnings calc, PDF/Word export, accountant review workflow, **accountant access role**). **Controls:** immutable audit metadata on entries; corrections only via reversal; period lock prevents edits; admin override requires reason + audit; attachments per entry; full tax-audit export; clear trace invoice→journal→payment.
**Test gate:** debits=credits invariants; period-lock prevents posting; reversal correction path; audit-file export validity.

### M12 — `custom_ai_chatbot` + website tracking + employee support app  `tag: m12-ai-chat`
**Deliverables:** consent-aware website tracking (sessions, pages, referrer, UTM, anonymization settings, visitor company only from form/email); website chat widget (configurable greeting, RAG answers, lead capture, product suggestions, transcript, sentiment, summary, next action, language detection/multi-language); **escalation** (low confidence, human requested, frustration/anger, legal/financial/medical high-risk, trigger words → route by availability/skill); **React employee support app** (live queue, accept/transfer, canned replies, AI suggested replies, customer/deal context, knowledge suggestions, mark resolved, create follow-up/quote/deal); notifications (browser push, email, optional WhatsApp/SMS).
**Test gate:** chat flow (visitor→RAG→cited answer→low-confidence escalation→transcript linked to lead); consent gating of tracking.

### M13 — `custom_helpdesk` + `custom_email_ai`  `tag: m13-helpdesk-email`
**Deliverables (helpdesk):** ticket/customer/contact/category/priority/SLA/status/assignee/team/skill/internal-note/external-reply/attachment + linked deal/order/invoice + AI summary/suggested-reply/approval-status; sources (email, chat, WhatsApp, social, phone, manual, portal); routing (category/customer/product/language/skill/availability/workload/priority/sentiment/SLA-risk); AI (summarize, classify, sentiment, suggest priority/assignee, draft reply, knowledge suggestion, follow-up, missing-info & complaint/legal-risk detection); **approval — AI replies never auto-sent by default**, pending→approve/edit/reject, edit reason stored for learning; SLA deadlines/warnings/escalation/dashboard; customer portal.
**Deliverables (email_ai):** connect mailbox (IMAP/SMTP + Graph), import emails, link to contact/company/deal/ticket, auto-create ticket/lead/finance-task by classification, AI draft reply, **pending outbox** (AI-drafted→review→approved→sent / rejected / needs-info), templates, signature, thread view, attachments, internal notes, audit. **Never auto-send by default**; optional limited auto-send only for low-risk categories after explicit admin config.
**Test gate:** email→ticket→AI classify→AI draft→employee edit→reason stored→send→close; pending-outbox state machine; SLA escalation timer.

### M14 — `custom_whatsapp_social`  `tag: m14-whatsapp-social`
**Deliverables (WhatsApp):** inbound/outbound, link to contact, create lead/ticket, AI draft + human approval, handoff, provider templates, media, history, opt-in/consent. **(Social inbox):** comments/messages/mentions (where API permits), link to contact, create ticket/lead, AI reply draft + approval, sentiment, escalation. **(Post planning):** content calendar, topics, campaigns, channels, AI-generated posts, manual edit, approval, scheduled publishing (where API permits), status, performance placeholder; topic calendar (recurring topics, frequency, channels, audience, tone, product focus, AI suggestions, employee approval).
**Approval blockers (flag):** Meta WhatsApp/Graph app review and X API tier are **external-approval** items — wire the integration and use sandbox/mock; request credentials/approval when needed.
**Test gate:** inbound webhook→contact link→AI draft→approval→send (mocked provider); scheduled-post state machine.

### M15 — `custom_ai_voice`  `tag: m15-ai-voice`
**Deliverables:** VoIP provider abstraction (Twilio/SIP), inbound webhook, call-flow builder, AI greeting, STT (Deepgram live / Whisper batch), TTS (ElevenLabs), RAG answers, escalation/transfer to employee, callback task, **call recording where lawful and enabled (consent + config)**, transcription, summarization, **structured sentiment** (calm/positive/neutral/confused/frustrated/angry/urgent — emojis optional in UI but **store structured labels**), call outcome classification, link to contact/deal/ticket, frustration warning, configurable escalation thresholds. Call-flow examples: sales, support, invoice, planning, rental availability, complaint, callback.
**Legal note:** call recording legality varies; gate behind explicit consent + per-jurisdiction config. Flag any region requiring two-party consent.
**Test gate:** inbound-call mock→STT→RAG→TTS loop with mocked providers; escalation threshold; sentiment label persistence.

### M16 — Hardening, dashboards, docs, full suite  `tag: m16-release`
**Deliverables:** all dashboards polished (CRM, finance, HR, rental, AI, helpdesk); cross-module dashboards; complete `docs/`; security review pass (RBAC matrix, record rules, company isolation, portal security, API auth, secret storage/encryption, audit logs for payroll/financial/signing/AI, document ACL, GDPR export/anonymize/consent/retention); full test suite green; demo + seed data; backup/restore verified; `docs/onboarding_client.md`.
**Test gate:** entire suite green in CI; security tests for every role; the end-to-end critical flows in Section 8 all pass.

---

## 6. Security & compliance (apply across all milestones)

- **RBAC roles:** Super admin, Company admin, Sales manager, Sales user, Finance manager, Accountant, HR manager, Payroll manager, Employee, Support manager, Support agent, Inventory manager, Rental manager, Social media manager, AI admin, Portal customer. Implement as Odoo groups + `ir.model.access.csv` + record rules.
- **Company isolation** via record rules; portal users see only their own data.
- **API auth:** scoped tokens for FastAPI services and the React app; never expose Odoo admin creds to the browser.
- **Secret storage:** secrets encrypted at rest (Odoo `ir.config_parameter` is **not** enough for keys — store provider keys encrypted via Fernet/`cryptography` with a key from env/secrets manager). `.env` for dev only.
- **Audit logs:** payroll access, financial records, signing events, AI outputs, admin overrides — all immutable and queryable.
- **GDPR:** contact-data export, delete/anonymize where legally allowed, consent fields, configurable retention policies; data-minimization on AI calls (redaction).
- **Data residency:** default RAG embeddings + payroll/financial AI to **local/EU**; external AI only with explicit opt-in.

---

## 7. Testing strategy (continuous — run after every milestone)

Create and maintain: unit tests (Odoo models), integration tests (workflows), API tests (FastAPI + Odoo controllers), security/access-rule tests, accounting-consistency tests, signing-audit tests, rental-availability tests, AI prompt tests (mocked providers), bank-matching tests, payroll-calculation tests (sample data), import/export tests, and UI smoke tests where feasible. CI (`.github/workflows/ci.yml`) runs lint + the full suite on every push; a milestone tag must be on a green CI run.

---

## 8. End-to-end critical flows that must pass (Definition-of-Done gates)

**Sales→cash:** create lead → convert to deal → create quote → send → customer accepts terms + signs → deal won → planning task created → invoice created → payment imported → matched → stock reduced → accounting entry posted.

**Rental:** create rental product → set per day/week/month price → rental quote → reserve → sign → pickup → return → damage registration → final invoice → stock back to available.

**Helpdesk:** email creates ticket → AI classifies → AI drafts reply → employee edits → reason stored → reply sent → ticket closed.

**AI chat:** visitor asks → AI searches RAG → answer with sources → low confidence routes to employee → transcript linked to contact/lead.

**Payroll:** create employee → create contract → configure salary → run payroll → generate payslip → publish to portal → create journal entry → export payroll report.

---

## 9. Value-add enhancements (build these — they differentiate the product)

1. **CI/CD pipeline** (GitHub Actions): lint → unit/integration tests → build Docker images → Trivy security scan → push.
2. **Sentry** error monitoring (backend + React) behind `SENTRY_DSN`.
3. **Observability profile** (Prometheus + Grafana + Loki) as an opt-in compose profile.
4. **Mollie payment links** on quotes/invoices (iDEAL) — major win for the Dutch market.
5. **GoCardless Bank Account Data (free PSD2)** as the live-bank-feed upgrade over file import.
6. **pre-commit hooks** (ruff, black, pylint-odoo, end-of-file/trailing-whitespace, secret-scan).
7. **Encrypted secrets at rest** for provider API keys (Fernet) + SOPS/age for prod manifests.
8. **AI cost & usage dashboard** per company (tokens, model, cost estimate) inside `custom_ai_core`.
9. **Prompt evaluation harness** (golden test cases per prompt template) to catch regressions in AI quality.
10. **Per-tenant data-residency switch** (local-only AI for sensitive tenants).
11. **Backup retention + restore drill** scripts with documented RPO/RTO.
12. **Staging compose profile** + seedable demo tenant for sales demos.
13. **OpenAPI docs** auto-generated for the FastAPI gateways.
14. **Rate limiting** on AI/integration gateways (Redis token bucket).
15. **Webhook signature verification** for all inbound providers (WhatsApp/Twilio/social/bank).

---

## 10. Definition of Done

The project is done only when: Odoo runs locally with all custom addons loaded; core CRM works; leads/deals/contacts/quotes/invoices work; signing works (MVP+); basic accounting works; bank import + matching prototype works; HRM portal works (leave, sick leave, payslip view); payroll has data model + payslip generation + export/reporting prototype; inventory works; rental workflow works; AI core works with mocked **and** real providers; RAG upload + cited answers work; helpdesk works; AI pending replies work; planning works; module licensing/activation works; dashboards present; access rights implemented; **all critical flows (Section 8) and the full test suite pass green in CI**; documentation complete; backup/restore verified.

---

## 11. `.env.example` (create this file; never require keys to boot locally)

```dotenv
# ── Odoo / DB ─────────────────────────────────────────────
ODOO_ADMIN_PASSWORD=
POSTGRES_DB=odoo
POSTGRES_USER=odoo
POSTGRES_PASSWORD=
# ── Redis / MinIO ─────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_BUCKET=platform-docs
# ── AI providers (optional; mock used if absent) ──────────
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
OLLAMA_BASE_URL=http://ollama:11434
AI_DEFAULT_DRAFTING_PROVIDER=anthropic
AI_DEFAULT_CLASSIFY_PROVIDER=openai
AI_EMBEDDINGS_PROVIDER=ollama
AI_ALLOW_EXTERNAL=false
AI_PRIVACY_REDACTION=true
# ── OCR (optional) ────────────────────────────────────────
MINDEE_API_KEY=
AZURE_DOCAI_ENDPOINT=
AZURE_DOCAI_KEY=
# ── Telephony / SMS / Voice (optional) ────────────────────
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
SIP_WEBHOOK_SECRET=
# ── WhatsApp (optional; needs Meta approval for Cloud API) ─
WHATSAPP_PROVIDER=meta            # meta | twilio | 360dialog
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=
# ── Email (optional; IMAP/SMTP always works) ──────────────
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
IMAP_HOST=
IMAP_USER=
IMAP_PASSWORD=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=
# ── Social (optional; needs app review) ───────────────────
META_APP_ID=
META_APP_SECRET=
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
X_API_KEY=
X_API_SECRET=
# ── Bank (optional; file import works without keys) ───────
GOCARDLESS_BANKDATA_SECRET_ID=
GOCARDLESS_BANKDATA_SECRET_KEY=
# ── Payments (optional) ───────────────────────────────────
MOLLIE_API_KEY=
STRIPE_API_KEY=
# ── Monitoring (optional) ─────────────────────────────────
SENTRY_DSN=
# ── Security ──────────────────────────────────────────────
APP_SECRET_ENCRYPTION_KEY=         # Fernet key for encrypting stored provider keys
INTERNAL_SERVICE_TOKEN=            # Odoo <-> FastAPI auth
```

---

## 12. Development log (keep updating in `docs/devlog.md`)

For each milestone record: **what was built**, **assumptions/defaults chosen**, **what remains**, **what needs API keys to activate**, **legal/compliance items needing external validation** (Dutch wage-tax filing, eIDAS qualified signatures, WhatsApp/Meta/X approval, call-recording consent per jurisdiction).

---

## 13. Start now

1. Inspect the repository; if empty, initialize the structure in Section 4.
2. Build the Docker/Odoo dev environment (M0).
3. Install the latest suitable Odoo Community (19, fallback 18).
4. Create the custom addons folder and the foundation modules (M1).
5. Run the system; fix errors.
6. Proceed milestone by milestone (M2 → M16), **running tests, fixing errors, committing and tagging after each**, continuing automatically until the platform is complete or a credential/legal/approval blocker forces a stop.

**Begin with M0 immediately.**
