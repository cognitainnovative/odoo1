# Cross-service tests

These complement the per-addon Odoo tests (`addons/*/tests`) and the gateway tests
(`services/*/tests`). They verify the system **as an integrated whole** against a running
stack.

```
tests/
├─ fixtures/        shared config, Odoo JSON-RPC client, sample data
├─ api/             API-level tests for the gateways + public Odoo controllers
└─ e2e/             the 5 Section-8 critical flows, end to end
```

## How they behave

- They run against a **live stack**. When a component is unreachable, the relevant test
  **skips** (with a reason) instead of failing — so the suite is green on a bare checkout
  and meaningful once the stack is up. This keeps CI honest without flaking.
- Signature-verification tests and PII-redaction assertions are **deterministic** and run
  without any stack.
- E2E flow tests fail **hard** if a documented workflow method is missing, but **tolerate**
  business-rule guards (e.g. a transition blocked because a precondition wasn't seeded).

## Running

```bash
# 1. Bring the stack up (dev override exposes host ports 8069/8000/8001)
docker compose up -d

# 2. Install test deps and run
pip install -r tests/requirements.txt
pytest tests                      # or: make test-e2e
```

## Configuration (env vars, with docker defaults)

| Var | Default | Meaning |
|---|---|---|
| `ODOO_URL` | `http://localhost:8069` | Odoo base URL |
| `ODOO_DB` | `platform_dev` | database name |
| `ODOO_USER` / `ODOO_PASSWORD` | `admin` / `admin` | login |
| `AI_GATEWAY_URL` | `http://localhost:8000` | AI gateway |
| `AI_GATEWAY_SECRET` | _empty_ | Bearer token if the gateway enforces auth |
| `INTEGRATION_GATEWAY_URL` | `http://localhost:8001` | integration gateway |

> For fully deterministic RAG/embedding assertions, set `EMBEDDING_PROVIDER=mock` on the
> ai-gateway; otherwise embedding-dependent checks skip when no Ollama backend is present.
