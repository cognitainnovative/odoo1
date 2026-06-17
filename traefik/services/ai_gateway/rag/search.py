"""RAG query: embed question → cosine search → cited answer via LLM."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RagChunk:
    doc_id: str
    doc_name: str
    chunk_index: int
    content: str
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass
class RagResult:
    answer: str
    chunks: list[RagChunk]
    provider: str
    model: str


async def rag_query(
    *,
    question: str,
    company_id: int,
    embed_provider,
    chat_provider,
    settings,
    database_url: str,
    system_prompt: str = "",
) -> RagResult:
    import json as _json

    from .db import get_pool

    embed_resp = await embed_provider.embed(question, model=settings.embedding_model)
    vec_str = "[" + ",".join(str(v) for v in embed_resp.embedding) + "]"

    pool = get_pool(database_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, doc_name, chunk_index, content, metadata,
                       COALESCE(1 - (embedding <=> %s::vector), 0) AS score
                FROM   rag_chunks
                WHERE  company_id = %s
                ORDER  BY score DESC
                LIMIT  %s
                """,
                (vec_str, company_id, settings.rag_top_k),
            )
            rows = cur.fetchall()
    finally:
        pool.putconn(conn)

    def _safe_score(raw) -> float:
        s = float(raw)
        return 0.0 if (s != s) else max(0.0, min(1.0, s))  # NaN from zero-vector cosine → 0.0

    chunks = [
        RagChunk(
            doc_id=r[0],
            doc_name=r[1] or r[0],
            chunk_index=r[2],
            content=r[3],
            metadata=r[4] if isinstance(r[4], dict) else _json.loads(r[4] or "{}"),
            score=_safe_score(r[5]),
        )
        for r in rows
    ]

    if not chunks:
        return RagResult(
            answer="I don't have enough information in the knowledge base to answer that.",
            chunks=[],
            provider=chat_provider.name,
            model="",
        )

    context = "\n\n".join(
        f"[Source {i+1}: {c.doc_name}]\n{c.content}" for i, c in enumerate(chunks)
    )
    sys = system_prompt or (
        "You are a helpful assistant. Answer the user's question using ONLY the provided context. "
        "Cite sources by their [Source N] label. If the context doesn't answer the question, say so."
    )
    from providers.base import ChatMessage

    messages = [ChatMessage(role="user", content=f"Context:\n{context}\n\nQuestion: {question}")]
    resp = await chat_provider.chat(messages, system=sys)

    return RagResult(answer=resp.content, chunks=chunks, provider=resp.provider, model=resp.model)
