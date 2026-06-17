-- Runs once on first container start via docker-entrypoint-initdb.d
-- The pgvector/pgvector:pg16 image ships the shared library; we just enable it.
CREATE EXTENSION IF NOT EXISTS vector;
