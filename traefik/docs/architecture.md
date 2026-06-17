# Architecture

This document describes the runtime topology of the platform as actually implemented in
this repository. It complements `modules.md` (per-addon detail) and `deployment.md`
(how to run it).

## Components

| Component | Tech | Container | Internal port | Host (dev) | Traefik host |
|---|---|---|---|---|---|
| Reverse proxy | Traefik v3 | `traefik` | 80/443/8080 | 80/443/8080 | `traefik.localhost` |
| ERP core | Odoo 19 Community + `custom_*` addons | `odoo` | 8069 | 8069 | `platform.localhost` |
| AI gateway | FastAPI | `ai-gateway` | 8000 | 8000 | `ai.localhost` |
| Integration gateway | FastAPI | `integration-gateway` | 8001 | 8001 | `hooks.localhost` |
| Support console | React + Vite + TS | `support-app` | 80 (nginx) / 5173 (dev) | 5173 | `support.localhost` |
| Background jobs | Celery worker | `celery-worker` | — | — | — |
| Scheduler | Celery beat | `celery-beat` | — | — | — |
| Database | PostgreSQL 16 + pgvector | `db` | 5432 | **5433** | — |
| Cache / broker | Redis 7 | `redis` | 6379 | 6379 | — |
| Object storage | MinIO (S3) | `minio` | 9000/9001 | 9000/9001 | `s3.localhost` / `minio.localhost` |

> The container Postgres is published on host `5433` so it never collides with a
> native Postgres on `5432`.

## Topology

```
                      ┌──────────────── Traefik (TLS, label routing) ───────────────┐
                      │                                                             │
            platform.localhost   ai.localhost   hooks.localhost   support.localhost  grafana.localhost*
                      │              │                │                  │
                 ┌────▼────┐   ┌─────▼──────┐   ┌─────▼────────┐   ┌─────▼──────┐
                 │  Odoo   │   │ ai_gateway │   │ integration_ │   │ support_app│
                 │ 19 + *  │   │ (FastAPI)  │   │ gateway      │   │ (React)    │
                 └──┬───┬──┘   └──┬──────┬──┘   └──┬───────────┘   └─────┬──────┘
                    │   │         │      │         │ JSON-RPC            │ JSON-RPC + bus
        JSON-RPC ───┘   │   pgvector  Redis        ▼                     ▼
                        │         │      │      ┌──Odoo────────────────────┐
                 ┌──────▼───┐ ┌───▼───┐ ┌▼────┐ │  (webhooks normalised in │
                 │ Postgres │ │ Redis │ │MinIO│ │   then forwarded back)   │
                 │+pgvector │ └───┬───┘ └─────┘ └──────────────────────────┘
                 └──────────┘     │
                          ┌───────▼────────┐
                          │ celery worker  │  queues: default, ai, accounting,
                          │ + celery beat  │          social, inventory, payroll,
                          └────────────────┘          reminders, ocr
 * grafana/prometheus only when the monitoring profile is enabled.
```

## Responsibility split

- **Odoo** owns all business data of record, the ORM, ACLs/record rules, accounting/HR/
  inventory engines, the customer & employee portals, and most UI. The 18 `custom_*`
  addons extend native models rather than replacing them.
- **ai_gateway** owns provider abstraction, the RAG pipeline (chunk → embed → pgvector →
  cited search), PII redaction before any external call, streaming chat, and the AI audit
  log. It holds no business data of record — only transient context. Endpoints:
  `/health`, `/chat`, `/chat/stream`, `/embed`, `/rag/ingest`, `/rag/query`,
  `/rag/document/{id}` (DELETE), `/rag/redact`, `/audit/logs`.
- **integration_gateway** receives inbound webhooks (WhatsApp, voice, social, bank),
  verifies provider signatures (Meta HMAC-SHA256, Twilio HMAC-SHA1), normalises payloads,
  and forwards into Odoo over JSON-RPC. Endpoints under `/webhooks/{whatsapp,social,voice,bank}`.
- **support_app** is the employee live console (queue, accept/transfer, canned + AI
  suggested replies, customer/deal context). It authenticates against an Odoo session and
  talks to Odoo JSON-RPC + the bus.
- **Celery** runs OCR, embeddings indexing, payroll runs, scheduled social posts,
  reminders, and reconciliation suggestions, brokered by Redis with `celery-beat` for cron.

## Multi-tenant / multi-company

Soft multi-tenant within a single instance uses Odoo `res.company` plus record rules for
isolation; portal users see only their own records. `custom_subscription_modules` gates
menus/routes per company. The hard-isolation path (database-per-tenant) is documented in
`deployment.md`. RAG documents and vectors are isolated per company in the `ai_gateway`
(see `ai.md`).

## Authentication between components

- Browser → Odoo: standard Odoo session.
- support_app → Odoo: Odoo session + scoped token; admin credentials never reach the browser.
- Odoo → ai_gateway: optional shared `Bearer` token (`AI_GATEWAY_SECRET` / `API_SECRET`);
  auth is skipped only when the secret is empty (dev).
- Provider → integration_gateway: per-provider signature verification; passes silently in
  dev when the relevant secret is unset, enforced as soon as it is set.

## Graceful degradation

The whole stack boots and runs core CRM, quoting, invoicing, inventory, rental, HRM,
planning and helpdesk with **no external API keys**. The AI gateway defaults to the `mock`
provider; OCR defaults to `mock`; WhatsApp/voice/social/bank/payments degrade to
draft/manual/file-import. Keys only unlock the corresponding live feature.
