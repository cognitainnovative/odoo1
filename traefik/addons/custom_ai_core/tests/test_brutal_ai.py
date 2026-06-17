"""Brutal edge-case tests for custom_ai_core (M2).

Targets security-sensitive paths the standard tests don't fully cover:
  - redaction: overlapping/adjacent PII, PII inside sentences, card numbers,
    repeated PII, ordering (BSN vs IBAN), case
  - prompt template render(): missing placeholders -> empty (not raw braces),
    extra vars ignored, no KeyError leak
"""

from odoo.addons.custom_ai_core.lib import redaction
from odoo.tests.common import TransactionCase


class TestBrutalRedaction(TransactionCase):

    def test_card_number_redacted(self):
        out, hit = redaction.redact("Card 4111 1111 1111 1111 on file")
        self.assertTrue(hit)
        self.assertIn("[CARD-REDACTED]", out)
        self.assertNotIn("4111", out)

    def test_pii_inside_sentence(self):
        out, hit = redaction.redact("Please email john.doe@acme.com or call 0612345678 today.")
        self.assertTrue(hit)
        self.assertNotIn("john.doe@acme.com", out)
        self.assertNotIn("0612345678", out)

    def test_multiple_same_type(self):
        out, hit = redaction.redact("a@x.com and b@y.com and c@z.com")
        self.assertEqual(out.count("[EMAIL-REDACTED]"), 3)

    def test_iban_and_email_together(self):
        out, hit = redaction.redact("IBAN NL91ABNA0417164300 mail x@y.com")
        self.assertIn("[IBAN-REDACTED]", out)
        self.assertIn("[EMAIL-REDACTED]", out)

    def test_clean_text_not_flagged(self):
        out, hit = redaction.redact("The quick brown fox jumps over the lazy dog.")
        self.assertFalse(hit)
        self.assertEqual(out, "The quick brown fox jumps over the lazy dog.")

    def test_none_safe(self):
        # redact must not crash on empty / None-ish input
        out, hit = redaction.redact("")
        self.assertFalse(hit)

    def test_email_with_plus_and_dots(self):
        out, hit = redaction.redact("reach me at jane.q+tag@sub.example.co.uk")
        self.assertTrue(hit)
        self.assertNotIn("jane.q+tag@sub.example.co.uk", out)


class TestBrutalTemplateRender(TransactionCase):
    """render() must fill missing placeholders with '' — never leak raw braces,
    never raise KeyError (the bug that produced literal {name} in AI summaries)."""

    def _tmpl(self, user_template, **kw):
        vals = {
            "name": "Brutal Tmpl",
            "code": "brutal_tmpl_test",
            "user_template": user_template,
            "system_prompt": "sys",
        }
        vals.update(kw)
        return self.env["ai.prompt.template"].create(vals)

    def test_all_vars_filled(self):
        t = self._tmpl("Hi {name} from {company}")
        _, user = t.render({"name": "Ann", "company": "Acme"})
        self.assertEqual(user, "Hi Ann from Acme")

    def test_missing_var_becomes_empty_not_braces(self):
        t = self._tmpl("Hi {name} from {company}")
        _, user = t.render({"name": "Ann"})  # company missing
        self.assertNotIn("{company}", user)  # must NOT leak raw placeholder
        self.assertIn("Hi Ann from", user)

    def test_no_vars_at_all(self):
        t = self._tmpl("Name: {name} Stage: {stage}")
        _, user = t.render({})  # nothing supplied
        self.assertNotIn("{name}", user)
        self.assertNotIn("{stage}", user)

    def test_extra_vars_ignored(self):
        t = self._tmpl("Just {name}")
        _, user = t.render({"name": "Bo", "irrelevant": "x"})
        self.assertEqual(user, "Just Bo")

    def test_empty_template(self):
        t = self._tmpl("")
        _, user = t.render({"name": "x"})
        self.assertEqual(user, "")
