# Development Log

## M0 — Foundation & Environment  `2026-06-04`

### What was built
- Project initialized at `/home/diviner/Odoo/custom/traefik/`
- Native dev environment (no Docker — Docker not installed on this machine)
- Odoo 19 Community at `/home/diviner/Odoo/19/` used as-is
- `config/odoo.conf` — port 8070, DB `platform_dev`, addons path wired
- `Makefile` with `up / down / restart / logs / shell / test / lint / format / init / seed / backup / restore / db-create / db-drop / db-reset / update / install-dev / check`
- All `scripts/` created and executable
- `docs/` skeleton created
- `.env.example` with all env-var placeholders from the brief
- `addons/` stub structure for all 16 custom modules (M1–M15)
- `.gitignore`, `pyproject.toml`, `.pre-commit-config.yaml` created
- `.github/workflows/ci.yml` created
- `git init` — branch: `main`

### Assumptions / defaults chosen
- **Port 8070** — 8069 already used by an existing Odoo instance (`test19test10` DB)
- **DB user: `diviner`** — PostgreSQL superuser already present; no separate `odoo` user needed in dev
- **No Docker** — native Python/Postgres setup; Docker can be added later (M0 extension)
- **pgvector** — enabled if available; graceful skip if `postgresql-16-pgvector` not installed
- **No Redis** — not installed; required for Celery/chat (M2/M12). Install: `sudo apt install redis`
- **No MinIO** — not installed; required for object storage. Optional for initial dev.

### What remains
- Run `make init` to create `platform_dev` DB and install Odoo base
- Run `make up` to start on port 8070
- Install custom addon modules milestone by milestone (M1 → M16)

### API keys needed to activate
- All AI features require `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (mock used otherwise)
- WhatsApp requires Meta app review (`WHATSAPP_ACCESS_TOKEN`)
- Voice requires `TWILIO_*` + `DEEPGRAM_API_KEY` + `ELEVENLABS_API_KEY`
- Bank live feed requires `GOCARDLESS_BANKDATA_*`
- Payments require `MOLLIE_API_KEY`

### Legal / compliance items needing external validation
- **Dutch wage-tax filing (loonaangifte)** — certified route required; not auto-submitted
- **eIDAS qualified signatures** — QTSP integration required if clients need qualified level
- **WhatsApp / Meta Cloud API** — requires Meta Business app review
- **Call recording** — two-party consent required in NL; gated behind explicit config

---

## M1 — Foundation Modules  `2026-06-12`

### What was built
Two Odoo 19 addons — `custom_theme` and `custom_subscription_modules`.

**`custom_theme`**
- `res.company` branding fields: `brand_primary_color`, `brand_secondary_color`, `brand_logo_url`, `brand_tagline`
- SCSS variable injection via `web._assets_primary_variables` asset bundle
- Login page zone container, portal override, backend `<head>` meta
- Email template branding inherit
- Admin dashboard shell (`/platform/dashboard` route + view)
- 5 tests — all passing

**`custom_subscription_modules`**
- Four models: `subscription.feature`, `subscription.package`, `subscription.subscription`, `subscription.usage.limit`
- Full state machine: `draft → trial → active → suspended → expired → cancelled`
- Menu gating via `ir.ui.menu._visible_menu_ids` override; gating skipped when `allowed_company_ids` absent from context (safe for query-count tests)
- Route guard decorator `@require_feature(code)` returning 403 when feature inactive
- 13 seeded packages + 12 feature codes with `root_menu_xmlid`
- `UNIQUE(company_id)` constraint on `subscription.subscription`
- License key generated (format `PLT-<uuid8>`) on first activation; stable on re-activation
- `subscription.usage.limit` model with per-period quota tracking
- 55 tests — all passing

### Test results
| Module | Tests | Result |
|---|---|---|
| custom_subscription_modules | 55 | ✅ all pass |
| custom_theme | 5 | ✅ all pass |

**Pre-existing Odoo core failures (not caused by our code):**
Confirmed by running the same tests on a clean install without our modules:
- `mail.tests.test_ir_ui_menu.TestMenuRootLookupByModel.test_look_for_existing_menu_root_user_with_access` — `3 > 2` and `1 > 0` query count failures in base Odoo 19.

### Odoo 19 gotchas discovered
- `Environment` in Odoo 19 has **no `with_context` method** — use `model_instance.with_context(...)` instead
- `@tools.ormcache` key expressions are evaluated in method scope via `unsafe_eval`; use simple field or argument references
- `ir.ui.menu.create/write/unlink` all call `env.registry.clear_cache()` — clears ALL ormcaches
- `allowed_company_ids` is never in context in test environments; guard against this when adding menu gating
- `models.Constraint(...)` replaces `_sql_constraints` in Odoo 19
- `@api.model_create_multi` required for `create` overrides

---

## M2 — AI Core  `2026-06-12`

### What was built

Two components — `addons/custom_ai_core` (Odoo 19 addon) and `services/ai_gateway` (FastAPI service).

**`custom_ai_core` Odoo addon**
- `ai.provider.config` — per-company provider configs with Fernet-encrypted API keys; `get_active_config()` helper with fallback
- `ai.prompt.template` + `ai.prompt.version` — versioned prompt templates; `action_new_version` creates a new draft, `get_template()` returns the active version, `render()` interpolates `{{variable}}` placeholders
- `ai.prompt.evaluation` — evaluation results linked to versions with score + pass/fail
- `ai.audit.log` — immutable audit trail; `create()` raises `ValidationError` on any write; all events have `event_type`, `prompt`, `response`, `tokens_used`, `model_used`, `company_id`
- `ai.document` — RAG document metadata with chunking state machine (`draft → indexing → indexed → error`); pgvector storage via `lib/task_bridge.py` and `lib/rag_index.py`
- `ai.correction` — correction/feedback store linked back to audit log entries
- `ai.service` — abstract mixin for models wanting AI capabilities
- `lib/providers.py` — abstract provider interface with Mock (no key), Anthropic, OpenAI; 768-dim zero-vector fallback embeddings
- `lib/task_bridge.py` — dispatches to Celery/Redis when available; falls back to synchronous execution
- Company isolation via record rules on every model

**`services/ai_gateway` FastAPI service**
- `providers/` — Mock / Anthropic / OpenAI / Azure / Ollama; `factory.py` selects by `provider_name` or falls back to mock
- `rag/ingest.py` — `_chunk()` (word-boundary splits with overlap), `_extract_text()` (plain/CSV/HTML), `ingest_document()` (pgvector insert with force/skip)
- `rag/search.py` — cosine similarity search with `COALESCE(1 - (embedding <=> %s::vector), 0)` to handle NaN from zero-vector embeddings; `_safe_score()` clamp
- `rag/db.py` — connection pool via `psycopg2.pool.ThreadedConnectionPool`; `ensure_schema()` creates `rag_chunks` with `vector(768)` column + pgvector extension
- `routers/rag.py` — `POST /rag/ingest`, `POST /rag/query`, `DELETE /rag/document/{doc_id}`, `POST /rag/redact`
- `redaction.py` — email, IBAN, Dutch phone (`(?<!\w)(?:\+31|0031|0)...` lookbehind for `+` prefix), BSN, credit card; `maybe_redact_messages()` for external-only redaction
- `audit.py` — append-only audit log written to PostgreSQL; `datetime.UTC` alias
- `tasks.py` — Celery app with `ingest_document_task` (base64 content, retries ×3, optional Odoo JSON-RPC callback)

### Test results

| Suite | Tests | Result |
|---|---|---|
| custom_ai_core (Odoo) | 45 | ✅ all pass |
| ai_gateway (pytest) | 37 | ✅ all pass |

**Gateway test breakdown:** 10 provider/mock, 13 redaction, 12 RAG ingest+search, 4 tenant isolation (company A never sees company B's chunks).

### Key implementation decisions

- **Zero-vector NaN fix** — pgvector cosine distance of two zero vectors is NaN; SQL uses `COALESCE(..., 0)` and Python `_safe_score()` clamps it to 0.0 rather than filtering it out (which would silently drop mock results)
- **Celery test isolation** — `unittest.mock.patch("...task_bridge.dispatch", return_value=False)` in `TestRag.setUp()` forces synchronous `_do_index()` path; Redis is live in dev so without the patch the task queues but no worker runs it
- **Unix socket PostgreSQL** — gateway tests use `postgresql:///platform_dev?user=diviner` (peer auth); TCP URLs require a password that peer-auth installs don't have
- **Dutch phone `\b` bug** — `\b` is a zero-width assertion between `\w` and `\W`; at a space→`+` boundary both characters are `\W` so `\b` never matches; replaced with `(?<!\w)` lookbehind

### Linters

```
ruff check addons/custom_ai_core/ services/ai_gateway/  → All checks passed!
black --check addons/custom_ai_core/ services/ai_gateway/ → 49 files would be left unchanged
```

---

## M1–M15 — All Core Modules  `2026-06-05`

### What was built (summary)
All 16 core modules (M1–M15) implemented and tagged:

| Tag | Module | Tests |
|---|---|---|
| m1-foundation-modules | custom_theme + custom_subscription_modules | 15/15 |
| m2-ai-core | custom_ai_core (providers, RAG, prompt store, audit) | 26/26 |
| m3-crm | custom_crm_core (AI scoring, campaigns, GDPR) | 17/17 |
| m4-signing | custom_quote_signing (portal signing, audit evidence) | 18/18 |
| m5-acct-basic | custom_accounting_basic (bank import, AI reconciliation) | 25/25 |
| m6-planning | custom_planning (jobs, calendar, resources) | 14/14 |
| m7-inventory | custom_inventory (bundles, auto-deduction, reorder AI) | 12/12 |
| m8-rental | custom_rental (full lifecycle, tiers, verification) | 26/26 |
| m9-hrm | custom_hrm (employees, sick leave, portal) | 15/15 |
| m10-payroll | custom_payroll_nl (Dutch engine, versioned rules) | 17/17 |
| m11-acct-advanced | custom_accounting_advanced (fiscal years, BV accounts) | 22/22 |
| m12-ai-chat | custom_ai_chatbot (chat widget, escalation) | 16/16 |
| m13-helpdesk-email | custom_helpdesk + custom_email_ai (SLA, outbox) | 22/22 |
| m14-whatsapp-social | custom_whatsapp_social (WA, inbox, calendar) | 23/23 |
| m15-ai-voice | custom_ai_voice (VoIP, sentiment, RAG) | 17/17 |

### Odoo 19 gotchas discovered (saved for future projects)
- `_sql_constraints` removed → use `models.Constraint("DEF", "msg")` as class attribute
- `type="html"` data fields: use real XML elements, NOT CDATA
- `res.groups.users` → `res.groups.user_ids`
- `hr.leave.type.requires_allocation` is Boolean (not "yes"/"no")
- `type='product'` for storable products removed → `type='consu'` + `is_storable=True`
- `account_reports` is Enterprise-only; `account.account` uses `company_ids` (M2M)
- `fetchmail` module removed in Odoo 19
- Kanban: `oe_kanban_bottom_left` → `footer//div[hasclass('d-flex')]`

---

## M16 — Hardening & Release  `2026-06-05`

### What was done
- Full test suite: **285/285 tests passing** across all 17 custom modules
- Documentation: onboarding_client.md, devlog.md updated, security.md
- Cross-module dashboard addons added
- Ruff lint clean on all addons

---

## Gap-fill pass — docs, observability, cross-service tests  `2026-06-17`

Audited the full repository against `CLAUDE_CODE_BUILD_BRIEF.md` §4/§7/§8/§10. All 18
addons, both FastAPI gateways, the Celery worker/beat, the React support app, the k8s Helm
chart, scripts, CI, and most docs were already present and complete. Three gaps were
found and closed:

### 1. Documentation (§4)
Added the seven missing reference docs, written from the actual code (not generic):
`architecture.md`, `deployment.md`, `accounting.md`, `payroll_nl.md`, `ai.md`,
`testing.md`, `upgrade_notes.md`.

### 2. Observability + dev compose (§4, value-add #3)
- `docker-compose.override.yml` — dev conveniences (Odoo `--dev=reload`, gateway `--reload`
  with source mounts, Vite HMR via the support_app `builder` stage, direct host ports).
- `docker-compose.monitoring.yml` — opt-in `monitoring` profile: Prometheus, Grafana, Loki,
  Promtail, node-exporter, cAdvisor; joins the external `platform_net`.
- `deploy/monitoring/**` — Prometheus scrape config, Loki + Promtail configs, Grafana
  datasource/dashboard provisioning, and a starter "Platform Overview" dashboard.
- `make monitoring-up` / `make monitoring-down`.

### 3. Cross-service tests (§4, §7, §8)
`tests/{fixtures,api,e2e}` were empty. Added a runnable suite (stdlib + requests):
- `fixtures/` — env-driven config, an Odoo JSON-RPC client, sample CAMT.053.
- `api/` — gateway endpoints (mock chat, redaction, RAG shape, tenant isolation), public
  chatbot controllers, and deterministic Meta/Twilio signature unit tests.
- `e2e/` — the five §8 critical flows (sales→cash asserts `debit == credit`; rental,
  helpdesk, payroll assert the documented action methods are wired; AI chat asserts a cited
  reply).
- Connectivity-gated: live tests **skip** when the stack is down, so CI is green on a bare
  checkout and meaningful when the stack is up. `make test-e2e` added.

Verified: ruff + black clean on `tests/`; suite collects 24 tests (7 deterministic pass,
17 skip without a live stack); all new YAML/JSON/XML parse.

### Still external (unchanged, by design)
Live API keys (Anthropic/OpenAI, WhatsApp/Meta review, Twilio/Deepgram/ElevenLabs, bank
PSD2, Mollie) and the certified Dutch **loonaangifte** filing route remain external sign-off
items — see `payroll_nl.md`.
