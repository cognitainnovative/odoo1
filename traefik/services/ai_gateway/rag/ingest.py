"""Document ingest: extract text → chunk → embed → store in pgvector."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from .db import get_pool


@dataclass
class IngestResult:
    doc_id: str
    chunks_stored: int
    skipped: bool = False


def _extract_text(content: bytes, mime: str) -> str:
    """Extract plain text from PDF, DOCX, CSV, HTML, or plain text bytes."""
    if mime == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return content.decode("utf-8", errors="replace")
    if mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        try:
            from docx import Document as DocxDocument

            doc = DocxDocument(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return content.decode("utf-8", errors="replace")
    if mime in ("text/csv", "application/csv", "text/tab-separated-values"):
        import csv

        text_io = io.StringIO(content.decode("utf-8", errors="replace"))
        reader = csv.reader(text_io)
        rows = [
            " | ".join(cell.strip() for cell in row)
            for row in reader
            if any(c.strip() for c in row)
        ]
        return "\n".join(rows)
    if mime in ("text/html", "text/xml", "application/xhtml+xml"):
        text = re.sub(r"<[^>]+>", " ", content.decode("utf-8", errors="replace"))
        return re.sub(r"\s+", " ", text).strip()
    return content.decode("utf-8", errors="replace")


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        i += size - overlap
    return [c for c in chunks if len(c.strip()) > 20]


async def ingest_document(
    *,
    doc_id: str,
    doc_name: str,
    content: bytes,
    mime: str,
    company_id: int,
    metadata: dict,
    embed_provider,
    settings,
    database_url: str,
    force: bool = False,
) -> IngestResult:
    pool = get_pool(database_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if not force:
                cur.execute(
                    "SELECT COUNT(*) FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    (doc_id, company_id),
                )
            if not force and cur.fetchone()[0] > 0:
                return IngestResult(doc_id=doc_id, chunks_stored=0, skipped=True)

            # Delete existing chunks before re-ingest
            cur.execute(
                "DELETE FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                (doc_id, company_id),
            )

        text = _extract_text(content, mime)
        chunks = _chunk(text, settings.chunk_size, settings.chunk_overlap)

        import json as _json

        for idx, chunk in enumerate(chunks):
            embed_resp = await embed_provider.embed(chunk, model=settings.embedding_model)
            vec_str = "[" + ",".join(str(v) for v in embed_resp.embedding) + "]"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rag_chunks
                        (company_id, doc_id, doc_name, chunk_index, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    (
                        company_id,
                        doc_id,
                        doc_name,
                        idx,
                        chunk,
                        vec_str,
                        _json.dumps(metadata),
                    ),
                )
        conn.commit()
        return IngestResult(doc_id=doc_id, chunks_stored=len(chunks))
    finally:
        pool.putconn(conn)
