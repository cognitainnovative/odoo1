"""RAG endpoints — document ingest, query, delete, and standalone redaction."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/rag", tags=["rag"])


class RagQueryRequest(BaseModel):
    question: str
    company_id: int = 0
    provider: str = ""
    model: str = ""
    system_prompt: str = ""


class RagChunkOut(BaseModel):
    doc_id: str
    doc_name: str
    chunk_index: int
    content: str
    score: float


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[RagChunkOut]
    provider: str
    model: str


class IngestResponse(BaseModel):
    doc_id: str
    chunks_stored: int
    skipped: bool


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    doc_id: str = Form(...),
    company_id: int = Form(0),
    force: bool = Form(False),
):
    from config import get_settings
    from providers.factory import get_embed_provider
    from rag.db import ensure_schema
    from rag.ingest import ingest_document

    settings = get_settings()
    ensure_schema(settings.database_url)
    embed_provider = get_embed_provider(settings)
    content = await file.read()
    mime = file.content_type or "text/plain"

    try:
        result = await ingest_document(
            doc_id=doc_id,
            doc_name=file.filename or doc_id,
            content=content,
            mime=mime,
            company_id=company_id,
            metadata={"filename": file.filename, "mime": mime},
            embed_provider=embed_provider,
            settings=settings,
            database_url=settings.database_url,
            force=force,
        )
    except Exception as exc:
        # Embedding backend / upstream dependency failure -> 502 (Bad Gateway),
        # not 500. Mirrors the /query and /delete handlers; lets clients (and
        # the test suite) distinguish "embeddings unavailable" from a genuine
        # server crash.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return IngestResponse(
        doc_id=result.doc_id, chunks_stored=result.chunks_stored, skipped=result.skipped
    )


@router.post("/query", response_model=RagQueryResponse)
async def query(req: RagQueryRequest):
    from config import get_settings
    from providers.factory import get_embed_provider, get_provider
    from rag.search import rag_query

    settings = get_settings()
    chat_provider = get_provider(req.provider, settings)
    embed_provider = get_embed_provider(settings)

    try:
        result = await rag_query(
            question=req.question,
            company_id=req.company_id,
            embed_provider=embed_provider,
            chat_provider=chat_provider,
            settings=settings,
            database_url=settings.database_url,
            system_prompt=req.system_prompt,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RagQueryResponse(
        answer=result.answer,
        sources=[
            RagChunkOut(
                doc_id=c.doc_id,
                doc_name=c.doc_name,
                chunk_index=c.chunk_index,
                content=c.content,
                score=round(c.score, 4),
            )
            for c in result.chunks
        ],
        provider=result.provider,
        model=result.model,
    )


class DeleteDocumentResponse(BaseModel):
    doc_id: str
    deleted_chunks: int


@router.delete("/document/{doc_id}", response_model=DeleteDocumentResponse)
async def delete_document(doc_id: str, company_id: int = 0):
    """Remove all pgvector rows for a document — embedding deletion."""
    from config import get_settings
    from rag.db import get_pool

    settings = get_settings()
    pool = get_pool(settings.database_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if company_id:
                cur.execute(
                    "DELETE FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    (doc_id, company_id),
                )
            else:
                cur.execute("DELETE FROM rag_chunks WHERE doc_id=%s", (doc_id,))
            deleted = cur.rowcount
        conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        pool.putconn(conn)
    return DeleteDocumentResponse(doc_id=doc_id, deleted_chunks=deleted)


class RedactRequest(BaseModel):
    text: str
    extra_patterns: list[list[str]] = []


class RedactResponse(BaseModel):
    original_length: int
    redacted_text: str
    was_changed: bool


@router.post("/redact", response_model=RedactResponse)
async def redact_text(req: RedactRequest):
    """Standalone redaction endpoint — returns redacted text and what was masked."""
    from redaction import redact

    extra = [(p[0], p[1]) for p in req.extra_patterns if len(p) == 2]
    redacted = redact(req.text, extra_patterns=extra if extra else None)
    return RedactResponse(
        original_length=len(req.text),
        redacted_text=redacted,
        was_changed=redacted != req.text,
    )
