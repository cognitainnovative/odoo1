"""Celery application and async tasks for ai_gateway.

Tasks:
  - ingest_document_task: chunk + embed + store in pgvector, then callback
    to Odoo to update ai.document.status.

Broker: Redis (REDIS_URL env var).
The gateway is the only component that does embedding compute — Odoo
triggers ingest via /rag/ingest and the Celery worker finishes it here.
"""

from __future__ import annotations

import asyncio
import logging
import os

from celery import Celery

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery("ai_gateway", broker=REDIS_URL, backend=REDIS_URL)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


@app.task(bind=True, name="ai_gateway.tasks.ingest_document", max_retries=3)
def ingest_document_task(
    self,
    doc_id: str,
    doc_name: str,
    content_b64: str,
    mime: str,
    company_id: int,
    metadata: dict,
    odoo_callback_url: str = "",
    odoo_db: str = "",
    odoo_doc_odoo_id: int = 0,
) -> dict:
    """Chunk, embed, and store a document in pgvector.

    Args:
        doc_id: Stable document identifier (used as the pgvector key).
        doc_name: Human-readable document name.
        content_b64: Base64-encoded file bytes.
        mime: MIME type for text extraction.
        company_id: Tenant identifier — always included in every pgvector row.
        metadata: Arbitrary JSON metadata stored alongside each chunk.
        odoo_callback_url: Optional Odoo JSON-RPC URL to POST status update.
        odoo_db: Odoo database name (for callback auth).
        odoo_doc_odoo_id: ai.document record ID to update (0 = no callback).

    Returns:
        {"doc_id": ..., "chunks_stored": ..., "status": "ok"|"error", "error": ...}
    """
    import base64

    try:
        from config import get_settings
        from providers.factory import get_embed_provider
        from rag.db import ensure_schema
        from rag.ingest import ingest_document

        settings = get_settings()
        ensure_schema(settings.database_url)
        embed_provider = get_embed_provider(settings)

        content = base64.b64decode(content_b64)

        result = asyncio.run(
            ingest_document(
                doc_id=doc_id,
                doc_name=doc_name,
                content=content,
                mime=mime,
                company_id=company_id,
                metadata=metadata,
                embed_provider=embed_provider,
                settings=settings,
                database_url=settings.database_url,
                force=True,
            )
        )

        status_payload = {
            "doc_id": doc_id,
            "chunks_stored": result.chunks_stored,
            "status": "ok",
            "error": "",
        }

        if odoo_callback_url and odoo_doc_odoo_id:
            _callback_odoo(odoo_callback_url, odoo_doc_odoo_id, "indexed", result.chunks_stored)

        logger.info(
            "ingest_document_task: doc_id=%s company_id=%s chunks=%d",
            doc_id,
            company_id,
            result.chunks_stored,
        )
        return status_payload

    except Exception as exc:
        logger.error("ingest_document_task failed for doc_id=%s: %s", doc_id, exc)
        if odoo_callback_url and odoo_doc_odoo_id:
            _callback_odoo(odoo_callback_url, odoo_doc_odoo_id, "error", 0, str(exc))
        raise self.retry(exc=exc, countdown=30) from exc


def _callback_odoo(
    callback_url: str,
    doc_id: int,
    status: str,
    chunk_count: int,
    error: str = "",
) -> None:
    """Fire-and-forget POST to Odoo JSON-RPC to update ai.document.status."""
    try:
        import requests

        internal_token = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
        requests.post(
            callback_url,
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": "ai.document",
                    "method": "gateway_status_callback",
                    "args": [[doc_id], status, chunk_count, error],
                },
            },
            headers={"X-Service-Token": internal_token},
            timeout=10,
        )
    except Exception as cb_exc:
        logger.warning("Odoo callback failed for doc_id=%d: %s", doc_id, cb_exc)
