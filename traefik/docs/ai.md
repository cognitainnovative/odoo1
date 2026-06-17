# AI subsystem

Two halves: the **`custom_ai_core`** Odoo addon (settings, prompt store, audit, the
correction-learning store, the Odoo-side client) and the **`ai_gateway`** FastAPI service
(provider abstraction, RAG, redaction, streaming). Odoo calls the gateway over an internal
authenticated channel; the gateway holds no business data of record.

## Providers

Configured in `ai_gateway/config.py` and per-company in `custom_ai_core`:

| Provider | Use | Key |
|---|---|---|
| `mock` | **default** — deterministic, no key, used in tests/CI and when no key is set | — |
| `anthropic` | complex/customer-facing drafting | `ANTHROPIC_API_KEY` |
| `openai` | fast classification/routing, fallback drafting | `OPENAI_API_KEY` |
| `azure` | data-residency tenants | `AZURE_OPENAI_*` |
| `ollama` | fully local / privacy mode, default embeddings | `OLLAMA_BASE_URL` |

Provider selection is an abstraction (`providers/factory.py`); switching providers is a
config change, not a code change. **Hard rule:** payroll and financial-record content is
never sent to an external provider unless the company explicitly opts in; default is
local/redacted only.

## Endpoints (`ai_gateway`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| POST | `/chat` | sync completion |
| POST | `/chat/stream` | SSE streaming completion |
| POST | `/embed` | embeddings |
| POST | `/rag/ingest` | ingest a document → chunk → embed → store in pgvector |
| POST | `/rag/query` | semantic search → answer with **citations + confidence** |
| DELETE | `/rag/document/{doc_id}` | delete a document **and its embeddings** |
| POST | `/rag/redact` | apply PII redaction to text |
| GET | `/audit/logs` | immutable AI audit log |

Interactive OpenAPI docs are served at `/docs` on each gateway.

## RAG pipeline

1. **Ingest** — PDF/DOCX/TXT/HTML/CSV → text → chunk (`chunk_size=512`, `overlap=64`) →
   embed → store in pgvector, tagged with `company_id` and `doc_id`.
2. **Query** — embed the question → vector search (`top_k=5`, `min_score=0.30`) →
   compose an answer with **source citations** and a **confidence score**; below the
   threshold the caller (helpdesk/chat/voice) escalates to a human.
3. **Delete / re-index** — removing a document deletes its embeddings too.

### Tenant isolation
Every vector row carries `company_id`; queries are filtered by it, so company A can never
retrieve company B's chunks. This is covered by `services/ai_gateway/tests/test_tenant_isolation.py`
and by `tests/api`.

## Redaction / data-minimization

`redaction.py` strips configured PII (emails, phone numbers, IBANs, etc.) before any
external provider call when `REDACT_PII_EXTERNAL=true` (default). The `mock` and `ollama`
local paths receive unredacted context since data never leaves the host. Covered by
`test_redaction.py`.

## Prompt store & correction-learning

`custom_ai_core` stores versioned prompt templates with evaluations and outputs, plus a
correction-learning store: original draft, edited reply, reason, category, knowledge
source, and an "add to KB?" flag. Edited replies enrich future prompt context — they are
**not** used for blind fine-tuning. AI replies are never auto-sent by default (helpdesk and
email_ai both use a pending → approve/edit/reject state machine).

## Cost & audit

The AI audit log records provider, model, token counts, and a cost estimate per company.
Every AI action (draft, classify, summarize, RAG answer) is logged and queryable for
traceability.

## Configuration quick reference

```
DEFAULT_PROVIDER=mock            # mock|anthropic|openai|ollama|azure
DEFAULT_MODEL=
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
RAG_TOP_K=5
RAG_MIN_SCORE=0.30
REDACT_PII_EXTERNAL=true
AI_GATEWAY_SECRET=               # Bearer token for Odoo→gateway; empty = open (dev only)
```
