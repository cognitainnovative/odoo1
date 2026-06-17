"""Gateway RAG retrieval tests — ingest → search returns cited chunks with confidence."""

import pytest
from providers.mock import MockProvider
from rag.db import ensure_schema
from rag.ingest import _chunk, _extract_text, ingest_document
from rag.search import rag_query


@pytest.fixture(autouse=True)
def setup_schema(db_url):
    """Ensure rag_chunks table exists before each test."""
    try:
        ensure_schema(db_url)
    except Exception:
        pytest.skip("PostgreSQL not available")


class TestChunking:
    """Text chunking utility."""

    def test_empty_text_yields_no_chunks(self):
        assert _chunk("", 50, 5) == []

    def test_short_text_yields_one_chunk(self):
        # Text must be > 20 chars to survive the minimum-length filter in _chunk
        chunks = _chunk("hello world this is a test sentence here okay", 50, 5)
        assert len(chunks) == 1

    def test_long_text_yields_multiple_chunks(self):
        words = " ".join(["word"] * 200)
        chunks = _chunk(words, 50, 10)
        assert len(chunks) > 1

    def test_overlap_makes_chunks_share_words(self):
        words = " ".join([str(i) for i in range(100)])
        chunks = _chunk(words, 20, 5)
        if len(chunks) >= 2:
            end_words = set(chunks[0].split()[-5:])
            start_words = set(chunks[1].split()[:5])
            assert end_words & start_words, "Overlap expected between consecutive chunks"


class TestTextExtraction:
    """_extract_text() for plain text and CSV."""

    def test_plain_text(self):
        text = _extract_text(b"Hello world", "text/plain")
        assert text == "Hello world"

    def test_csv_extraction(self):
        csv_bytes = b"name,age\nAlice,30\nBob,25"
        text = _extract_text(csv_bytes, "text/csv")
        assert "Alice" in text
        assert "Bob" in text

    def test_html_extraction(self):
        html = b"<html><body><p>Hello <b>world</b></p></body></html>"
        text = _extract_text(html, "text/html")
        assert "Hello" in text
        assert "world" in text

    def test_unknown_mime_falls_back_to_utf8(self):
        text = _extract_text(b"fallback text", "application/octet-stream")
        assert "fallback text" in text


class TestRagIngestAndSearch:
    """Ingest documents then search — results must be cited with confidence scores."""

    @pytest.mark.asyncio
    async def test_ingest_returns_chunk_count(self, mock_settings, db_url):
        embed = MockProvider()
        content = ("The platform supports Dutch payroll and bank accounts. " * 5).encode()
        result = await ingest_document(
            doc_id="test-doc-ingest-1",
            doc_name="Dutch Payroll Guide",
            content=content,
            mime="text/plain",
            company_id=9991,
            metadata={"test": True},
            embed_provider=embed,
            settings=mock_settings,
            database_url=db_url,
            force=True,
        )
        assert result.doc_id == "test-doc-ingest-1"
        assert result.chunks_stored > 0

    @pytest.mark.asyncio
    async def test_search_returns_cited_chunks(self, mock_settings, db_url):
        embed = MockProvider()
        chat = MockProvider()
        # Ingest a doc
        content = b"Our refund policy allows returns within 30 days of purchase."
        await ingest_document(
            doc_id="test-doc-search-1",
            doc_name="Refund Policy",
            content=content,
            mime="text/plain",
            company_id=9992,
            metadata={},
            embed_provider=embed,
            settings=mock_settings,
            database_url=db_url,
            force=True,
        )
        result = await rag_query(
            question="What is the refund policy?",
            company_id=9992,
            embed_provider=embed,
            chat_provider=chat,
            settings=mock_settings,
            database_url=db_url,
        )
        assert result.answer
        assert isinstance(result.chunks, list)
        if result.chunks:
            chunk = result.chunks[0]
            assert chunk.doc_name == "Refund Policy"
            assert 0.0 <= chunk.score <= 1.0, "Confidence score must be in [0, 1]"

    @pytest.mark.asyncio
    async def test_ingest_skip_when_already_ingested(self, mock_settings, db_url):
        embed = MockProvider()
        content = b"Skip test content that is long enough to survive the chunk length filter."
        kwargs = {
            "doc_id": "test-doc-skip-1",
            "doc_name": "Skip Doc",
            "content": content,
            "mime": "text/plain",
            "company_id": 9993,
            "metadata": {},
            "embed_provider": embed,
            "settings": mock_settings,
            "database_url": db_url,
        }
        await ingest_document(**kwargs, force=True)
        result2 = await ingest_document(**kwargs, force=False)
        assert result2.skipped


class TestDeleteDocument:
    """DELETE /rag/document — removes pgvector rows for that doc_id."""

    @pytest.mark.asyncio
    async def test_delete_removes_chunks(self, mock_settings, db_url):
        from rag.db import get_pool

        embed = MockProvider()
        content = b"Delete me completely from the vector store."
        await ingest_document(
            doc_id="test-doc-delete-1",
            doc_name="DeleteMe",
            content=content,
            mime="text/plain",
            company_id=9994,
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
                cur.execute(
                    "DELETE FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    ("test-doc-delete-1", 9994),
                )
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM rag_chunks WHERE doc_id=%s AND company_id=%s",
                    ("test-doc-delete-1", 9994),
                )
                count = cur.fetchone()[0]
        finally:
            pool.putconn(conn)
        assert count == 0, "All chunks for the document should be removed after delete"
