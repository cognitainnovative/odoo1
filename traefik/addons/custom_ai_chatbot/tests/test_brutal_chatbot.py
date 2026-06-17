"""Brutal edge-case tests for custom_ai_chatbot (M12).

Targets the compliance/safety-critical paths:
  - HIGH-RISK escalation (medical/financial/legal) — bot must NOT answer, must route
  - escalation ORDERING (trigger word wins; high-risk before RAG answer)
  - consent gating: NO tracking without consent; revoke STOPS tracking immediately
  - transcript linked to lead on lead creation (test gate)
  - process_message always returns the documented contract keys
"""

from odoo.tests.common import TransactionCase


class _ChatBase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.session = self.env["chat.session"].create({"visitor_id": self.visitor.id})

    def _send(self, text):
        return self.env["chat.session"].process_message(self.session.id, text)


class TestBrutalHighRiskEscalation(_ChatBase):
    """High-risk medical/financial/legal topics must escalate, never get an AI answer."""

    def test_medical_question_escalates(self):
        r = self._send("What medication should I take for my chest pain?")
        self.assertTrue(
            r["escalated"], "Medical-advice question must escalate, not be answered by the bot."
        )
        self.assertEqual(r["escalation_reason"], "high_risk")

    def test_financial_advice_escalates(self):
        r = self._send("Should I invest my pension savings in your company?")
        self.assertTrue(r["escalated"])
        self.assertEqual(r["escalation_reason"], "high_risk")

    def test_legal_term_escalates(self):
        # legal terms are in ESCALATION_TRIGGERS -> trigger_word (also acceptable)
        r = self._send("I want to file a lawsuit against you")
        self.assertTrue(r["escalated"])
        self.assertIn(r["escalation_reason"], ("trigger_word", "high_risk"))

    def test_ordinary_product_question_not_high_risk(self):
        # Must NOT over-escalate a normal pricing/product question.
        r = self._send("What is the price of your starter plan?")
        # Either answered, or escalated for a non-high-risk reason — but not high_risk.
        if r["escalated"]:
            self.assertNotEqual(r["escalation_reason"], "high_risk")


class TestBrutalEscalationOrdering(_ChatBase):
    """Trigger/human-request/high-risk are checked before the AI answers."""

    def test_human_request_beats_ai_answer(self):
        r = self._send("Please connect me to a human agent")
        self.assertTrue(r["escalated"])
        self.assertEqual(r["escalation_reason"], "human_requested")

    def test_escalated_response_has_contract_keys(self):
        r = self._send("I am so frustrated, this is ridiculous")
        for key in ("reply", "escalated", "escalation_reason", "citations", "session_id"):
            self.assertIn(key, r)
        self.assertEqual(r["escalation_reason"], "sentiment")


class TestBrutalConsentGating(TransactionCase):
    """Consent is required for tracking; revoke stops it immediately (GDPR)."""

    def setUp(self):
        super().setUp()
        self.visitor = self.env["chat.visitor"].get_or_create_visitor()

    def test_no_tracking_without_consent(self):
        self.visitor.record_page_view(url="/home")
        self.visitor.record_page_view(url="/pricing")
        self.assertEqual(
            self.visitor.page_view_count, 0, "Tracking must not happen without consent."
        )

    def test_tracking_after_consent(self):
        self.visitor.record_consent()
        self.visitor.record_page_view(url="/home")
        self.visitor.record_page_view(url="/pricing")
        self.assertEqual(self.visitor.page_view_count, 2)

    def test_revoke_stops_tracking_immediately(self):
        self.visitor.record_consent()
        self.visitor.record_page_view(url="/a")
        self.assertEqual(self.visitor.page_view_count, 1)
        self.visitor.revoke_consent()
        # further views must NOT be recorded
        self.visitor.record_page_view(url="/b")
        self.visitor.record_page_view(url="/c")
        self.assertEqual(
            self.visitor.page_view_count,
            1,
            "Revoking consent must immediately stop tracking (GDPR Art. 7(3)).",
        )

    def test_reconsent_after_revoke_resumes(self):
        self.visitor.record_consent()
        self.visitor.record_page_view(url="/a")
        self.visitor.revoke_consent()
        self.visitor.record_page_view(url="/b")  # blocked
        self.visitor.record_consent()  # re-consent clears revoked date
        self.visitor.record_page_view(url="/c")  # allowed again
        self.assertEqual(self.visitor.page_view_count, 2)


class TestBrutalTranscriptToLead(_ChatBase):
    """Transcript must link to the lead when a lead is created from the chat."""

    def test_lead_created_links_session(self):
        self.session.visitor_email = "lead@test.local"
        self.session.visitor_name = "Lead Person"
        self._send("Hi, I'm interested in your product")
        self.session.action_create_lead()
        # session should now reference a lead (field name may vary)
        lead = getattr(self.session, "lead_id", False)
        self.assertTrue(lead, "Creating a lead from chat must link the lead to the session.")
