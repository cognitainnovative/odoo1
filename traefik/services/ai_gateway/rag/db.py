"""PostgreSQL connection pool for RAG vector operations."""

from __future__ import annotations

import psycopg2
import psycopg2.pool

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pool(database_url: str) -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, dsn=database_url)
    return _pool


def ensure_schema(database_url: str) -> None:
    """Create the rag_chunks table with pgvector column if it doesn't exist."""
    pool = get_pool(database_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id          BIGSERIAL PRIMARY KEY,
                    company_id  INTEGER NOT NULL DEFAULT 0,
                    doc_id      VARCHAR(255) NOT NULL,
                    doc_name    VARCHAR(512),
                    chunk_index INTEGER NOT NULL DEFAULT 0,
                    content     TEXT NOT NULL,
                    embedding   vector(768),
                    metadata    JSONB DEFAULT '{}',
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS rag_chunks_company_idx ON rag_chunks (company_id);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
                ON rag_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
        conn.commit()
    finally:
        pool.putconn(conn)
