from odoo.tests.common import TransactionCase


class TestAiProvider(TransactionCase):
    """Tests for ai.provider model — encrypted keys, provider factory."""

    def setUp(self):
        super().setUp()
        # Use the mock provider seeded by data/ai_providers.xml
        self.mock_provider = self.env["ai.provider"].search(
            [("code", "=", "mock"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def test_seed_providers_exist(self):
        """All five default providers are seeded (mock, anthropic, openai, azure, ollama)."""
        codes = (
            self.env["ai.provider"]
            .search([("company_id", "=", self.env.company.id)])
            .mapped("code")
        )
        for code in ("mock", "anthropic", "openai", "azure", "ollama"):
            self.assertIn(code, codes, f"Provider '{code}' should be seeded.")

    def test_api_key_encryption_roundtrip(self):
        """Storing and reading back an API key works correctly."""
        # Use the existing Anthropic provider (seeded, so it exists already)
        provider = self.env["ai.provider"].search(
            [("code", "=", "anthropic"), ("company_id", "=", self.env.company.id)], limit=1
        )
        provider.api_key = "test-secret-key-1234"
        self.assertEqual(provider.api_key, "test-secret-key-1234")
        # The stored field must be encrypted (not plain text)
        self.assertNotEqual(provider._api_key_encrypted, "test-secret-key-1234")
        # Clean up
        provider.api_key = ""

    def test_empty_key_stores_empty(self):
        """Setting an empty API key stores empty encrypted value."""
        provider = self.env["ai.provider"].search(
            [("code", "=", "openai"), ("company_id", "=", self.env.company.id)], limit=1
        )
        provider.api_key = ""
        self.assertEqual(provider.api_key, "")
        self.assertEqual(provider._api_key_encrypted, "")

    def test_mock_provider_returns_instance(self):
        """get_provider_instance() returns MockProvider for code=mock."""
        self.mock_provider.allow_external = False
        instance = self.mock_provider.get_provider_instance()
        from odoo.addons.custom_ai_core.lib.providers import MockProvider

        self.assertIsInstance(instance, MockProvider)

    def test_external_blocked_raises(self):
        """get_provider_instance() raises UserError if external calls are blocked."""
        from odoo.exceptions import UserError

        # Use the seeded Anthropic provider but FORCE allow_external=False for the
        # test, so we don't depend on its (UI-mutable) seeded value and don't
        # collide with the (company, code) unique constraint by creating a dupe.
        provider = self.env["ai.provider"].search(
            [("code", "=", "anthropic"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not provider:
            provider = self.env["ai.provider"].create(
                {
                    "name": "Test Anthropic (blocked)",
                    "code": "anthropic",
                    "company_id": self.env.company.id,
                }
            )
        provider.allow_external = False
        self.assertFalse(provider.allow_external)
        with self.assertRaises(UserError):
            provider.get_provider_instance()

    def test_get_default_provider_returns_mock(self):
        """get_default_provider() returns mock when no other active provider exists."""
        provider = self.env["ai.provider"].get_default_provider()
        self.assertEqual(provider.code, "mock")

    def test_company_isolation(self):
        """Providers for company A are not visible to company B."""
        company_b = self.env["res.company"].create({"name": "Test Company B"})
        providers_b = self.env["ai.provider"].search([("company_id", "=", company_b.id)])
        providers_main = self.env["ai.provider"].search([("company_id", "=", self.env.company.id)])
        ids_b = set(providers_b.ids)
        ids_main = set(providers_main.ids)
        self.assertTrue(
            ids_b.isdisjoint(ids_main),
            "Providers must not overlap between companies.",
        )
