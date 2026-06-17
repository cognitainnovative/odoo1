"""Brutal edge-case tests for custom_crm_core (M3).

Targets the things our review fixed but the standard tests don't fully cover:
  - lead_score bounds (never < 0, never > 100, negative/huge revenue)
  - duplicate detection: case-insensitive email, company-scoped
"""

from odoo.tests.common import TransactionCase


class TestBrutalLeadScore(TransactionCase):

    def _lead(self, **kw):
        vals = {"name": "Score Lead", "type": "lead"}
        vals.update(kw)
        return self.env["crm.lead"].create(vals)

    def test_score_never_exceeds_100(self):
        lead = self._lead(
            email_from="a@b.com",
            phone="0612345678",
            expected_revenue=99999999.0,
            probability=90,
            partner_name="Big Co",
        )
        lead._compute_lead_score()
        self.assertLessEqual(lead.lead_score, 100)

    def test_negative_revenue_does_not_make_negative_score(self):
        lead = self._lead(expected_revenue=-50000.0, probability=10)
        lead._compute_lead_score()
        self.assertGreaterEqual(lead.lead_score, 0)

    def test_huge_revenue_capped(self):
        lead = self._lead(expected_revenue=10_000_000.0)
        lead._compute_lead_score()
        self.assertLessEqual(lead.lead_score, 100)
        self.assertGreaterEqual(lead.lead_score, 0)

    def test_empty_lead_score_zero_or_low(self):
        lead = self._lead()
        lead._compute_lead_score()
        self.assertGreaterEqual(lead.lead_score, 0)
        self.assertLessEqual(lead.lead_score, 100)


class TestBrutalDuplicateDetection(TransactionCase):

    def test_case_insensitive_email_match(self):
        a = self.env["crm.lead"].create(
            {"name": "Dup A", "type": "lead", "email_from": "Match@Example.com"}
        )
        b = self.env["crm.lead"].create(
            {"name": "Dup B", "type": "lead", "email_from": "match@example.com"}
        )
        a._compute_duplicates()
        # b (same email, different case) must be detected as a duplicate of a
        self.assertIn(b.id, a.duplicate_lead_ids.ids)

    def test_different_email_not_duplicate(self):
        a = self.env["crm.lead"].create({"name": "X", "type": "lead", "email_from": "x@a.com"})
        self.env["crm.lead"].create({"name": "Y", "type": "lead", "email_from": "y@b.com"})
        a._compute_duplicates()
        self.assertEqual(a.duplicate_count, 0)

    def test_short_company_name_not_matched(self):
        # partner_name length <= 3 should not drive a duplicate match
        a = self.env["crm.lead"].create({"name": "A", "type": "lead", "partner_name": "AB"})
        self.env["crm.lead"].create({"name": "B", "type": "lead", "partner_name": "AB"})
        a._compute_duplicates()
        self.assertEqual(a.duplicate_count, 0)
