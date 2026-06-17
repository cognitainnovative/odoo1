from odoo.tests.common import TransactionCase


class TestRedaction(TransactionCase):
    """Tests for PII redaction utility."""

    def setUp(self):
        super().setUp()
        from odoo.addons.custom_ai_core.lib.redaction import redact

        self.redact = redact

    def test_email_redacted(self):
        text, changed = self.redact("Contact us at info@example.com for help.")
        self.assertNotIn("info@example.com", text)
        self.assertIn("[EMAIL-REDACTED]", text)
        self.assertTrue(changed)

    def test_iban_redacted(self):
        text, changed = self.redact("Please pay to NL91ABNA0417164300.")
        self.assertIn("[IBAN-REDACTED]", text)
        self.assertTrue(changed)

    def test_no_pii_unchanged(self):
        plain = "The weather is nice today."
        text, changed = self.redact(plain)
        self.assertEqual(text, plain)
        self.assertFalse(changed)

    def test_empty_string(self):
        text, changed = self.redact("")
        self.assertEqual(text, "")
        self.assertFalse(changed)

    def test_multiple_pii_types(self):
        raw = "Email: test@test.com, IBAN: NL91ABNA0417164300"
        text, changed = self.redact(raw)
        self.assertIn("[EMAIL-REDACTED]", text)
        self.assertIn("[IBAN-REDACTED]", text)
        self.assertTrue(changed)

    def test_bsn_redacted(self):
        text, changed = self.redact("Mijn BSN is 123456789.")
        self.assertNotIn("123456789", text)
        self.assertIn("[BSN-REDACTED]", text)
        self.assertTrue(changed)

    def test_dutch_phone_redacted(self):
        text, changed = self.redact("Bel me op 0612345678.")
        self.assertNotIn("0612345678", text)
        self.assertIn("[PHONE-REDACTED]", text)
        self.assertTrue(changed)

    def test_international_phone_redacted(self):
        text, changed = self.redact("International: +31612345678")
        self.assertIn("[PHONE-REDACTED]", text)
        self.assertTrue(changed)
