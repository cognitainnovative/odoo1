from odoo.tests.common import TransactionCase


class TestRag(TransactionCase):
    """Tests for RAG knowledge base — document indexing and retrieval."""

    def _create_doc(self, name="Test Doc", content="The quick brown fox jumps over the lazy dog."):
        return self.env["ai.document"].create(
            {"name": name, "company_id": self.env.company.id, "content": content}
        )

    def test_create_document(self):
        doc = self._create_doc()
        self.assertEqual(doc.status, "draft")
        self.assertEqual(doc.chunk_count, 0)

    def test_index_document_creates_chunks(self):
        doc = self._create_doc(content="Word " * 200)
        doc.action_index()
        self.assertEqual(doc.status, "indexed")
        self.assertGreater(doc.chunk_count, 0)

    def test_delete_index_removes_chunks(self):
        doc = self._create_doc(content="Word " * 200)
        doc.action_index()
        self.assertGreater(doc.chunk_count, 0)
        doc.action_delete_index()
        self.assertEqual(doc.chunk_count, 0)
        self.assertEqual(doc.status, "draft")

    def test_keyword_search_returns_results(self):
        doc = self._create_doc(
            content="The platform supports Dutch payroll and IBAN bank accounts."
        )
        doc.action_index()
        results = self.env["ai.document.chunk"].search_similar(
            "Dutch payroll", company_id=self.env.company.id
        )
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["source"], "Test Doc")

    def test_company_isolation_in_search(self):
        """Documents from company A must not appear in company B's search."""
        company_b = self.env["res.company"].create({"name": "Isolation Test Co"})
        doc = self._create_doc(content="Confidential data from company A.")
        doc.action_index()

        results = self.env["ai.document.chunk"].search_similar(
            "Confidential", company_id=company_b.id
        )
        sources = [r["source"] for r in results]
        self.assertNotIn("Test Doc", sources, "Company B should not see Company A's documents.")

    def test_rag_augmented_call(self):
        doc = self._create_doc(content="Our refund policy is 30 days from purchase.")
        doc.action_index()
        result = self.env["ai.service"].call_with_rag("What is the refund policy?")
        self.assertTrue(result["ok"])
        self.assertIn("citations", result)
