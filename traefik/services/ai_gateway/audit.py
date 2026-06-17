"""AI audit log — write every AI call to Postgres for compliance + learning."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_logger = logging.getLogger(__name__)


async def log_ai_event(
    *,
    database_url: str,
    event_type: str,  # chat | embed | rag | stream
    provider: str,
    model: str,
    company_id: int = 0,
    user_id: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    redacted: bool = False,
    metadata: dict | None = None,
) -> None:
    """Insert one row into ai_audit_log (fire-and-forget, errors are logged not raised)."""
    try:
        from rag.db import get_pool

        pool = get_pool(database_url)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_audit_log
                        (event_type, provider, model, company_id, user_id,
                         prompt_tokens, completion_tokens, latency_ms,
                         redacted, metadata, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        event_type,
                        provider,
                        model,
                        company_id,
                        user_id,
                        prompt_tokens,
                        completion_tokens,
                        latency_ms,
                        redacted,
                        json.dumps(metadata or {}),
                        datetime.now(UTC),
                    ),
                )
            conn.commit()
        finally:
            pool.putconn(conn)
    except Exception as exc:
        _logger.warning("audit log failed: %s", exc)


def ensure_audit_schema(database_url: str) -> None:
    from rag.db import get_pool

    pool = get_pool(database_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_audit_log (
                    id               BIGSERIAL PRIMARY KEY,
                    event_type       VARCHAR(32) NOT NULL,
                    provider         VARCHAR(64),
                    model            VARCHAR(128),
                    company_id       INTEGER DEFAULT 0,
                    user_id          INTEGER DEFAULT 0,
                    prompt_tokens    INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    latency_ms       INTEGER DEFAULT 0,
                    redacted         BOOLEAN DEFAULT FALSE,
                    metadata         JSONB DEFAULT '{}',
                    created_at       TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ai_audit_company_idx ON ai_audit_log (company_id, created_at DESC);"
            )
        conn.commit()
    finally:
        pool.putconn(conn)
