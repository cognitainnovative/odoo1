from odoo.tests.common import TransactionCase


class TestAiService(TransactionCase):
    """Tests for ai.service — mock provider, audit log, redaction, RAG."""

    def test_call_with_mock_returns_ok(self):
        """ai.service.call() returns ok=True when mock provider is active."""
        result = self.env["ai.service"].call("Hello, what is 2+2?")
        self.assertTrue(result["ok"], f"Expected ok=True, got error: {result.get('error')}")
        self.assertIn("MOCK", result["content"])

    def test_call_creates_audit_log(self):
        """Every ai.service.call() creates an audit log entry."""
        before = self.env["ai.audit.log"].search_count([("company_id", "=", self.env.company.id)])
        self.env["ai.service"].call("Test prompt")
        after = self.env["ai.audit.log"].search_count([("company_id", "=", self.env.company.id)])
        self.assertEqual(after, before + 1, "An audit log entry should be created per call.")

    def test_call_with_system_prompt(self):
        """System prompt is passed through correctly."""
        result = self.env["ai.service"].call("Say hello", system_prompt="You are a pirate.")
        self.assertTrue(result["ok"])

    def test_redaction_applied(self):
        """PII in the prompt is redacted before sending when privacy_mode is True."""
        # Enable privacy mode on mock provider
        provider = self.env["ai.provider"].search(
            [("code", "=", "mock"), ("company_id", "=", self.env.company.id)], limit=1
        )
        provider.privacy_mode = True

        result = self.env["ai.service"].call("Email me at secret@company.com")
        # The audit log entry should indicate redaction happened
        log = self.env["ai.audit.log"].browse(result["audit_log_id"])
        self.assertTrue(log.was_redacted, "PII should be detected and redaction flag set.")

    def test_template_code_resolves(self):
        """Calling with a valid template_code uses that template's prompts."""
        result = self.env["ai.service"].call(
            "fallback",
            template_code="crm_lead_summary",
            template_vars={"name": "Test Lead", "company": "Acme", "stage": "New", "notes": ""},
        )
        self.assertTrue(result["ok"])

    def test_audit_log_immutable(self):
        """Audit log entries are unconditionally immutable after creation."""
        from odoo.exceptions import UserError

        result = self.env["ai.service"].call("Test")
        log = self.env["ai.audit.log"].browse(result["audit_log_id"])
        with self.assertRaises(UserError):
            log.write({"status": "error"})


class TestMockProvider(TransactionCase):
    """Direct tests for the MockProvider class."""

    def test_mock_call_returns_response(self):
        from odoo.addons.custom_ai_core.lib.providers import AiMessage, MockProvider

        provider = MockProvider()
        resp = provider.call([AiMessage(role="user", content="Hello")])
        self.assertTrue(resp.ok)
        self.assertIn("MOCK", resp.content)
        self.assertGreater(resp.output_tokens, 0)

    def test_mock_embed_returns_vector(self):
        from odoo.addons.custom_ai_core.lib.providers import MockProvider

        provider = MockProvider()
        vec = provider.embed("some text")
        self.assertEqual(len(vec), 128)
        self.assertEqual(vec[0], 0.0)


class TestPromptEvaluation(TransactionCase):
    """Tests for ai.prompt.evaluation — run evaluations against templates."""

    def setUp(self):
        super().setUp()
        self.template = self.env["ai.prompt.template"].search(
            [
                ("code", "=", "crm_lead_summary"),
                ("company_id", "=", self.env.company.id),
                ("is_active", "=", True),
            ],
            limit=1,
        )

    def _make_eval(self, name="Test eval", expected_contains="MOCK"):
        return self.env["ai.prompt.evaluation"].create(
            {
                "template_id": self.template.id,
                "company_id": self.env.company.id,
                "name": name,
                "test_input_json": '{"name": "Acme", "company": "Test Co", "stage": "New", "notes": ""}',
                "expected_contains": expected_contains,
            }
        )

    def test_evaluation_created(self):
        """Evaluation record is created correctly."""
        ev = self._make_eval()
        self.assertEqual(ev.template_id, self.template)
        self.assertFalse(ev.passed)
        self.assertFalse(ev.run_date)

    def test_evaluation_run_passes(self):
        """action_run() with mock provider and 'MOCK' in expected_contains → passed=True."""
        ev = self._make_eval(expected_contains="MOCK")
        ev.action_run()
        self.assertTrue(ev.passed, "Mock response contains 'MOCK' so eval should pass.")
        self.assertTrue(ev.run_date)
        self.assertTrue(ev.run_by)

    def test_evaluation_run_fails_on_wrong_expected(self):
        """action_run() with an expectation the mock can't meet → passed=False."""
        ev = self._make_eval(expected_contains="DEFINITELY_NOT_IN_MOCK_RESPONSE_XYZ")
        ev.action_run()
        self.assertFalse(ev.passed)

    def test_evaluation_run_invalid_json(self):
        """action_run() with invalid JSON logs an error and sets passed=False."""
        ev = self._make_eval()
        ev.test_input_json = "not valid json {"
        ev.action_run()
        self.assertFalse(ev.passed)
        self.assertTrue(ev.error)

    def test_run_all_for_template(self):
        """run_all_for_template returns a summary list with pass/fail per eval."""
        self._make_eval(name="e1", expected_contains="MOCK")
        self._make_eval(name="e2", expected_contains="DEFINITELY_NOT_IN_RESPONSE")
        results = self.env["ai.prompt.evaluation"].run_all_for_template("crm_lead_summary")
        self.assertEqual(len(results), 2)
        names = {r["name"] for r in results}
        self.assertIn("e1", names)
        self.assertIn("e2", names)


class TestAzureProviderPlaceholder(TransactionCase):
    """Tests for the Azure OpenAI provider placeholder."""

    def test_azure_provider_instance_created(self):
        """get_provider('azure') returns AzureOpenAiProvider."""
        from odoo.addons.custom_ai_core.lib.providers import AzureOpenAiProvider, get_provider

        p = get_provider("azure", api_key="dummy", base_url="", model="gpt-4o")
        self.assertIsInstance(p, AzureOpenAiProvider)

    def test_azure_provider_no_endpoint_returns_error(self):
        """Azure provider with no base_url returns error response (not an exception)."""
        from odoo.addons.custom_ai_core.lib.providers import AiMessage, get_provider

        p = get_provider("azure", api_key="dummy", base_url="")
        resp = p.call([AiMessage(role="user", content="Hello")])
        self.assertFalse(resp.ok)
        self.assertIn("endpoint", resp.error.lower())
