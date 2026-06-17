"""Audit log query endpoint."""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntry(BaseModel):
    id: int
    event_type: str
    provider: str
    model: str
    company_id: int
    user_id: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    redacted: bool
    created_at: datetime


@router.get("/logs", response_model=list[AuditEntry])
async def get_logs(
    company_id: int = Query(0),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    from config import get_settings
    from rag.db import get_pool

    settings = get_settings()
    pool = get_pool(settings.database_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, event_type, provider, model, company_id, user_id,
                       prompt_tokens, completion_tokens, latency_ms, redacted, created_at
                FROM   ai_audit_log
                WHERE  (%s = 0 OR company_id = %s)
                ORDER  BY created_at DESC
                LIMIT  %s OFFSET %s
                """,
                (company_id, company_id, limit, offset),
            )
            rows = cur.fetchall()
    finally:
        pool.putconn(conn)

    return [
        AuditEntry(
            id=r[0],
            event_type=r[1],
            provider=r[2],
            model=r[3],
            company_id=r[4],
            user_id=r[5],
            prompt_tokens=r[6],
            completion_tokens=r[7],
            latency_ms=r[8],
            redacted=r[9],
            created_at=r[10],
        )
        for r in rows
    ]
