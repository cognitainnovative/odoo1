"""Pytest fixtures for ai_gateway tests.

All tests run without any external network calls — providers use MockProvider.
Database operations use a temporary in-memory or temp Postgres DB (or psycopg2 mock).
"""

import asyncio
import os
import sys

import pytest

# Ensure the gateway app module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings(tmp_path):
    """Settings with mock provider and Unix-socket DB URL (peer auth, no password needed)."""
    from config import Settings

    return Settings(
        api_secret="test-secret",
        database_url=os.environ.get("TEST_DATABASE_URL", "postgresql:///platform_dev?user=diviner"),
        redis_url="redis://localhost:6379/0",
        default_provider="mock",
        embedding_provider="mock",
        embedding_model="mock-embed",
        embedding_dimensions=768,
        chunk_size=50,
        chunk_overlap=5,
        rag_top_k=3,
        rag_min_score=0.0,
        redact_pii_external=True,
    )


@pytest.fixture
def mock_provider():
    from providers.mock import MockProvider

    return MockProvider()


@pytest.fixture(autouse=True)
def reset_db_pool():
    """Reset the module-level psycopg2 pool before each test.

    rag/db.py caches a pool singleton; resetting ensures each test
    gets a fresh connection with the correct URL.
    """
    import rag.db as _db

    _db._pool = None
    yield
    _db._pool = None


@pytest.fixture
def db_url():
    # TCP auth requires a password; use Unix socket (peer auth) in dev.
    return os.environ.get("TEST_DATABASE_URL", "postgresql:///platform_dev?user=diviner")
