"""Tenant isolation tests — company A's chunks never appear in company B's search results."""

import pytest
from providers.mock import MockProvider
from rag.db import ensure_schema, get_pool
from rag.ingest import ingest_document
from rag.search import rag_query

COMPANY_A = 88801
COMPANY_B = 88802


@pytest.fixture(autouse=True)
def setup_schema(db_url):
    try:
        ensure_schema(db_url)
    except Exception:
        pytest.skip("PostgreSQL not available")


@pytest.fixture(autouse=True)
def cleanup_isolation_data(setup_schema, db_url):
    """Remove test rows before and after each test.

    Explicitly depends on setup_schema so schema is guaranteed to exist
    (and skip is applied) before we try to connect.
    """
    pool = get_pool(db_url)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rag_chunks WHERE company_id IN (%s, %s)",
                (COMPANY_A, COMPANY_B),
            )
        conn.commit()
    finally:
        pool.putconn(conn)
    yield
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rag_chunks WHERE company_id IN (%s, %s)",
                (COMPANY_A, COMPANY_B),
            )
        conn.commit()
    finally:
        pool.putconn(conn)


class TestTenantIsolation:
    """Company A's query must NEVER return company B's chunks."""

    @pytest.mark.asyncio
    async def test_company_a_cannot_see_company_b_chunks(self, mock_settings, db_url):
        embed = MockProvider()
        chat = MockProvider()

        # Ingest a doc for company B only
        await ingest_document(
            doc_id="isolation-b-doc-1",
            doc_name="Company B Secret",
            content=b"This is strictly confidential company B payroll data.",
            mime="text/plain",
            company_id=COMPANY_B,
            metadata={},
            embed_provider=embed,
            settings=mock_settings,
            database_url=db_url,
            force=True,
        )

        # Query as company A — must not see company B's doc
        result = await rag_query(
            question="company B payroll data",
            company_id=COMPANY_A,
            embed_provider=embed,
            chat_provider=chat,
            settings=mock_settings,
            database_url=db_url,
        )
        sources = [c.doc_name for c in result.chunks]
        assert (
            "Company B Secret" not in sources
        ), "Company A's RAG query must not return Company B's documents"

    @pytest.mark.asyncio
    async def test_company_b_cannot_see_company_a_chunks(self, mock_settings, db_url):
        embed = MockProvider()
        chat = MockProvider()

        await ingest_document(
            doc_id="isolation-a-doc-1",
            doc_name="Company A Confidential",
            content=b"Company A internal strategy document. Top secret.",
            mime="text/plain",
            company_id=COMPANY_A,
            metadata={},
            embed_provider=embed,
            settings=mock_settings,
            database_url=db_url,
            force=True,
        )

        result = await rag_query(
            question="Company A internal strategy",
            company_id=COMPANY_B,
            embed_provider=embed,
            chat_provider=chat,
            settings=mock_settings,
            database_url=db_url,
        )
        sources = [c.doc_name for c in result.chunks]
        assert (
            "Company A Confidential" not in sources
        ), "Company B's RAG query must not return Company A's documents"

    @pytest.mark.asyncio
    async def test_each_company_only_sees_own_chunks(self, mock_settings, db_url):
        embed = MockProvider()
        chat = MockProvider()

        await ingest_document(
            doc_id="iso-both-a",
            doc_name="Alpha Document",
            content=b"Alpha document exclusive to tenant A.",
            mime="text/plain",
            company_id=COMPANY_A,
            metadata={},
            embed_provider=embed,
            settings=mock_settings,
            database_url=db_url,
            force=True,
        )
        await ingest_document(
            doc_id="iso-both-b",
            doc_name="Beta Document",
            content=b"Beta document exclusive to tenant B.",
            mime="text/plain",
            company_id=COMPANY_B,
            metadata={},
            embed_provider=embed,
            settings=mock_settings,
            database_url=db_url,
            force=True,
        )

        result_a = await rag_query(
            question="Alpha exclusive tenant A",
            company_id=COMPANY_A,
            embed_provider=embed,
            chat_provider=chat,
            settings=mock_settings,
            database_url=db_url,
        )
        result_b = await rag_query(
            question="Beta exclusive tenant B",
            company_id=COMPANY_B,
            embed_provider=embed,
            chat_provider=chat,
            settings=mock_settings,
            database_url=db_url,
        )

        sources_a = {c.doc_name for c in result_a.chunks}
        sources_b = {c.doc_name for c in result_b.chunks}

        assert "Beta Document" not in sources_a, "Company A must not see Beta Document"
        assert "Alpha Document" not in sources_b, "Company B must not see Alpha Document"

    @pytest.mark.asyncio
    async def test_delete_document_removes_only_target(self, mock_settings, db_url):
        embed = MockProvider()

        for company_id, doc_id, name in [
            (COMPANY_A, "del-test-a", "Doc A"),
            (COMPANY_B, "del-test-b", "Doc B"),
        ]:
            await ingest_document(
                doc_id=doc_id,
                doc_name=name,
                content=b"Deletion test content.",
                mime="text/plain",
                company_id=company_id,
                metadata={},
                embed_provider=embed,
                settings=mock_settings,
                database_url=db_url,
                force=True,
            )

        pool = get_pool(db_url)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                # Delete only company A's doc
                cur.execute(
                    "DELETE FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    ("del-test-a", COMPANY_A),
                )
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    ("del-test-a", COMPANY_A),
                )
                count_a = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    ("del-test-b", COMPANY_B),
                )
                count_b = cur.fetchone()[0]
        finally:
            pool.putconn(conn)

        assert count_a == 0, "Company A's doc should be deleted"
        assert count_b > 0, "Company B's doc should remain untouched"
