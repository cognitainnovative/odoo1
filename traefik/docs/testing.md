# Testing

The suite has three layers. CI runs the first two on every push; the third runs against a
live stack (locally or in a deploy pipeline).

## 1. Per-addon Odoo tests — `addons/*/tests`

Standard Odoo `TransactionCase` tests, one or more per addon, covering models, workflows,
security/access rules, and the milestone test gates from the brief (signing audit, rental
availability, accounting consistency, payroll calculation, etc.). Run them with:

```bash
make test                      # all addons that have a tests/ dir
./scripts/run_tests.sh m5-acct-basic custom_crm_core   # narrow to specific addons
```

## 2. Gateway tests — `services/*/tests`

`pytest` suites for the FastAPI services:
- `ai_gateway/tests` — mock provider, RAG retrieval, redaction, tenant isolation.
- (integration_gateway signature logic is also unit-tested from `tests/api`, see below.)

```bash
pip install -r services/ai_gateway/requirements.txt
pytest services/ai_gateway/tests
```

## 3. Cross-service tests — `tests/`

These verify the integrated system. See `tests/README.md` for details.

```
tests/
├─ fixtures/   shared config, Odoo JSON-RPC client, sample CAMT.053
├─ api/        gateway endpoints + public Odoo controllers + signature unit tests
└─ e2e/        the 5 Section-8 critical flows
```

Run against a live stack:

```bash
docker compose up -d
pip install -r tests/requirements.txt
pytest tests          # or: make test-e2e
```

**Behaviour by design:**
- Deterministic checks (Meta/Twilio signature verification, PII redaction) run with no stack
  and always assert real outcomes.
- Live checks **skip with a clear reason** when a component is unreachable, so the suite is
  green on a bare checkout and meaningful once the stack is up — no false failures, no flakes.
- E2E flow tests fail **hard** if a documented workflow method is missing, and **tolerate**
  business-rule guards (a transition blocked by an unseeded precondition).

### The five critical flows (`tests/e2e`)

| File | Flow | Strongest assertion |
|---|---|---|
| `test_sales_to_cash.py` | lead → order → invoice → post | posted move has `debit == credit` |
| `test_rental_lifecycle.py` | quote → … → close | every `rental.order` action method is wired |
| `test_helpdesk_flow.py` | ticket → AI classify → draft → send → close | pending-reply state machine wired |
| `test_payroll_flow.py` | run → calculate → … → post journal | run methods wired + access-log model present |
| `test_ai_chat_flow.py` | visitor → message → cited reply | reply + `escalated` + `citations` returned |

## CI

`.github/workflows/ci.yml`:
1. **syntax-check** — `py_compile` every addon `.py`, parse every addon `.xml`.
2. **lint** — `ruff check` and `black --check` on `addons/` and `tests/`.
3. **test** — spin up `pgvector/pgvector:pg16`, check out Odoo 19, enable pgvector, assert
   DB/pgvector connectivity, run every addon's Odoo tests, then run the gateway pytest suites.

To also run the cross-service `tests/` in CI, add a job that brings the stack up with
`docker compose up -d`, waits for `/web/health` and the gateway `/health` endpoints, then
runs `pytest tests` (set `EMBEDDING_PROVIDER=mock` for deterministic RAG assertions).

## Reports

A rendered HTML report from a prior full run is kept at `docs/test_report.html`.
