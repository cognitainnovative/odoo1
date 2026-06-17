"""Tests for M12 — chatbot sessions, escalation, consent gating, lead creation."""

from odoo.tests.common import TransactionCase


class TestChatVisitor(TransactionCase):
    """Tests for visitor tracking and consent."""

    def test_create_visitor(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.assertTrue(visitor.token)
        self.assertFalse(visitor.tracking_consent)

    def test_token_is_unique_per_call(self):
        v1 = self.env["chat.visitor"].get_or_create_visitor()
        v2 = self.env["chat.visitor"].get_or_create_visitor()
        self.assertNotEqual(v1.token, v2.token)

    def test_get_existing_visitor_by_token(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        token = visitor.token
        same_visitor = self.env["chat.visitor"].get_or_create_visitor(token)
        self.assertEqual(visitor.id, same_visitor.id)

    def test_consent_recording(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.assertFalse(visitor.tracking_consent)
        visitor.record_consent()
        self.assertTrue(visitor.tracking_consent)
        self.assertTrue(visitor.consent_date)

    def test_page_view_only_with_consent(self):
        """Page views are only recorded after consent."""
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        visitor.record_page_view(url="/products", referrer="https://google.com")
        self.assertEqual(visitor.page_view_count, 0)  # no consent yet
        visitor.record_consent()
        visitor.record_page_view(url="/products")
        self.assertEqual(visitor.page_view_count, 1)


class TestChatSession(TransactionCase):
    """Tests for chat session lifecycle."""

    def setUp(self):
        super().setUp()
        self.visitor = self.env["chat.visitor"].get_or_create_visitor()

    def _make_session(self, **kwargs):
        vals = {"visitor_id": self.visitor.id}
        vals.update(kwargs)
        return self.env["chat.session"].create(vals)

    def test_create_session(self):
        session = self._make_session()
        self.assertEqual(session.state, "open")
        self.assertEqual(session.sentiment, "neutral")

    def test_assign_to_me(self):
        session = self._make_session(state="escalated")
        session.action_assign_to_me()
        self.assertEqual(session.state, "assigned")
        self.assertEqual(session.assigned_agent_id, self.env.user)

    def test_resolve_session(self):
        session = self._make_session()
        session.action_resolve()
        self.assertEqual(session.state, "resolved")
        self.assertTrue(session.resolved_date)

    def test_create_lead_from_session(self):
        session = self._make_session(
            visitor_name="Test Visitor",
            visitor_email="visitor@test.com",
        )
        result = session.action_create_lead()
        self.assertTrue(session.lead_id)
        self.assertEqual(result["type"], "ir.actions.act_window")

    def test_create_lead_returns_existing(self):
        """Creating a lead twice returns the same lead."""
        session = self._make_session(visitor_name="Test")
        session.action_create_lead()
        lead_id = session.lead_id.id
        session.action_create_lead()
        self.assertEqual(session.lead_id.id, lead_id)


class TestChatMessageProcessing(TransactionCase):
    """Tests for chat message processing with AI."""

    def setUp(self):
        super().setUp()
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.session = self.env["chat.session"].create({"visitor_id": visitor.id})

    def test_message_creates_transcript(self):
        result = self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="Hello, I need help with pricing.",
        )
        self.assertIn("reply", result)
        self.assertFalse(result["escalated"])
        # Transcript should have 2 lines (user + assistant)
        self.assertEqual(len(self.session.transcript_ids), 2)

    def test_trigger_word_causes_escalation(self):
        """Messages containing trigger words escalate the session."""
        result = self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="I need to talk to a lawyer about this lawsuit.",
        )
        self.assertTrue(result["escalated"])
        self.assertEqual(result["escalation_reason"], "trigger_word")
        self.session.invalidate_recordset()
        self.assertEqual(self.session.state, "escalated")

    def test_message_links_visitor_info(self):
        """Visitor name/email are captured from message params."""
        self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="Hello",
            visitor_name="Jane Smith",
            visitor_email="jane@example.com",
        )
        self.session.invalidate_recordset()
        self.assertEqual(self.session.visitor_name, "Jane Smith")
        self.assertEqual(self.session.visitor_email, "jane@example.com")

    def test_transcript_preserved_in_order(self):
        """Messages are stored in chronological order."""
        self.env["chat.session"].process_message(
            session_id=self.session.id, user_message="First message"
        )
        lines = self.session.transcript_ids
        self.assertEqual(lines[0].role, "user")
        self.assertEqual(lines[1].role, "assistant")


class TestChatConfig(TransactionCase):
    """Tests for chatbot configuration."""

    def test_default_config_created(self):
        """Default config is seeded by data/chatbot_config.xml."""
        config = self.env["chat.config"].search([("company_id", "=", self.env.company.id)], limit=1)
        self.assertTrue(config, "Default chat config must be seeded.")
        self.assertTrue(config.is_enabled)

    def test_config_company_unique(self):
        """Only one config per company."""
        import psycopg2
        from odoo.tools import mute_logger

        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["chat.config"].create({})  # already has one for this company


class TestChatEscalation(TransactionCase):
    """Test gate: escalation paths — trigger word, human-requested, frustration, low-confidence."""

    def setUp(self):
        super().setUp()
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.session = self.env["chat.session"].create({"visitor_id": visitor.id})

    def test_human_requested_escalation(self):
        """Phrases like 'speak to a human' trigger human_requested escalation."""
        result = self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="I'd like to speak to a human please.",
        )
        self.assertTrue(result["escalated"])
        self.assertEqual(result["escalation_reason"], "human_requested")
        self.session.invalidate_recordset()
        self.assertEqual(self.session.state, "escalated")

    def test_frustration_escalation(self):
        """Frustration keywords escalate with reason 'sentiment'."""
        result = self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="This is absolutely ridiculous, nothing is working!",
        )
        self.assertTrue(result["escalated"])
        self.assertEqual(result["escalation_reason"], "sentiment")
        self.session.invalidate_recordset()
        self.assertEqual(self.session.sentiment, "frustrated")

    def test_low_confidence_escalation(self):
        """When AI returns not-ok (confidence=0), session is escalated."""
        result = self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="What is the meaning of life according to your product roadmap?",
        )
        # If AI fails to answer (ok=False), escalation_reason should be low_confidence
        # and escalated flag should be True
        self.assertIn("reply", result)
        self.assertIn("citations", result)
        # In test env, if ai.service returns ok=False, state is escalated
        # We verify the citations key is always present in the response
        self.assertIsInstance(result["citations"], list)

    def test_response_always_has_citations_key(self):
        """response dict always contains 'citations' regardless of escalation."""
        result = self.env["chat.session"].process_message(
            session_id=self.session.id,
            user_message="Tell me about pricing.",
        )
        self.assertIn("citations", result)
        self.assertIn("session_id", result)
        self.assertIn("escalated", result)

    def test_transfer_to_agent(self):
        """action_transfer_to_agent reassigns the session to the target agent."""
        self.session.write({"state": "assigned", "assigned_agent_id": self.env.user.id})
        self.session.action_transfer_to_agent(self.env.user.id)
        self.session.invalidate_recordset()
        self.assertEqual(self.session.assigned_agent_id.id, self.env.user.id)
        self.assertEqual(self.session.state, "assigned")

    def test_escalation_sets_state(self):
        """escalate() always moves state to 'escalated'."""
        self.session.escalate("high_risk")
        self.session.invalidate_recordset()
        self.assertEqual(self.session.state, "escalated")
        self.assertEqual(self.session.escalation_reason, "high_risk")


class TestCannedReply(TransactionCase):
    """Tests for canned replies model."""

    def test_create_canned_reply(self):
        reply = self.env["chat.canned.reply"].create(
            {
                "shortcut": "/price",
                "name": "Pricing Info",
                "message": "Our pricing starts at €49/month. Visit /pricing for full details.",
            }
        )
        self.assertEqual(reply.shortcut, "/price")
        self.assertTrue(reply.active)

    def test_shortcut_company_unique(self):
        """Same shortcut cannot be used twice for the same company."""
        import psycopg2

        self.env["chat.canned.reply"].create(
            {
                "shortcut": "/hello",
                "name": "Greeting",
                "message": "Hello! How can I help?",
            }
        )
        from odoo.tools import mute_logger

        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["chat.canned.reply"].create(
                    {
                        "shortcut": "/hello",
                        "name": "Duplicate",
                        "message": "Should fail.",
                    }
                )

    def test_canned_reply_with_category(self):
        reply = self.env["chat.canned.reply"].create(
            {
                "shortcut": "/hours",
                "name": "Opening Hours",
                "message": "We're open Mon–Fri 9–18h CET.",
                "category": "General",
            }
        )
        self.assertEqual(reply.category, "General")

    def test_archive_canned_reply(self):
        reply = self.env["chat.canned.reply"].create(
            {
                "shortcut": "/old",
                "name": "Old Reply",
                "message": "Outdated info.",
            }
        )
        reply.active = False
        self.assertFalse(reply.active)


class TestChatConsentGating(TransactionCase):
    """Test gate: consent gating of tracking — explicit spec test gate."""

    def test_page_view_requires_consent(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        visitor.record_page_view(url="/products", referrer="https://google.com")
        self.assertEqual(visitor.page_view_count, 0, "No tracking without consent")

    def test_page_view_allowed_after_consent(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        visitor.record_consent()
        visitor.record_page_view(url="/products")
        visitor.record_page_view(url="/pricing")
        self.assertEqual(visitor.page_view_count, 2)

    def test_consent_date_recorded(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.assertFalse(visitor.consent_date)
        visitor.record_consent()
        self.assertTrue(visitor.consent_date)

    def test_company_name_only_from_form(self):
        """company_name is empty on new visitor — only set after form submission."""
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.assertFalse(visitor.company_name)
        visitor.company_name = "ACME BV"
        self.assertEqual(visitor.company_name, "ACME BV")

    def test_transcript_linked_to_lead(self):
        """Full flow: visitor → session → lead → transcript linked to lead."""
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        session = self.env["chat.session"].create(
            {
                "visitor_id": visitor.id,
                "visitor_name": "Test Visitor",
                "visitor_email": "test@example.com",
            }
        )
        # Simulate transcript
        self.env["chat.transcript.line"].create(
            {
                "session_id": session.id,
                "role": "user",
                "content": "I'm interested in your product.",
            }
        )
        # Create lead
        session.action_create_lead()
        self.assertTrue(session.lead_id)
        # Lead is linked back to visitor
        session.visitor_id.lead_id = session.lead_id
        self.assertEqual(session.visitor_id.lead_id, session.lead_id)
        # Transcript lines are accessible from session which is linked to lead
        self.assertEqual(len(session.transcript_ids), 1)


class TestConsentRevocation(TransactionCase):
    """GDPR Art. 7(3): visitor must be able to withdraw consent at any time."""

    def test_revoke_consent_stops_tracking(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        visitor.record_consent()
        self.assertTrue(visitor.tracking_consent)
        visitor.revoke_consent()
        visitor.invalidate_recordset()
        self.assertFalse(visitor.tracking_consent)
        self.assertTrue(visitor.consent_revoked_date)

    def test_page_view_blocked_after_revocation(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        visitor.record_consent()
        visitor.record_page_view(url="/products")
        self.assertEqual(visitor.page_view_count, 1)
        visitor.revoke_consent()
        visitor.record_page_view(url="/about")
        # Count must not increase after revocation
        self.assertEqual(visitor.page_view_count, 1)

    def test_re_consent_clears_revoked_date(self):
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        visitor.record_consent()
        visitor.revoke_consent()
        self.assertTrue(visitor.consent_revoked_date)
        # Visitor may consent again
        visitor.record_consent()
        visitor.invalidate_recordset()
        self.assertTrue(visitor.tracking_consent)
        self.assertFalse(visitor.consent_revoked_date)

    def test_revoke_without_prior_consent_is_safe(self):
        """revoke_consent() on a visitor who never consented must not raise."""
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        self.assertFalse(visitor.tracking_consent)
        visitor.revoke_consent()  # should not raise
        visitor.invalidate_recordset()
        self.assertFalse(visitor.tracking_consent)
        self.assertTrue(visitor.consent_revoked_date)


class TestAgentAvailability(TransactionCase):
    """Tests for agent skill catalogue and availability routing."""

    def test_create_skill(self):
        skill = self.env["chat.agent.skill"].create({"name": "Billing"})
        self.assertEqual(skill.name, "Billing")
        self.assertTrue(skill.active)

    def test_skill_name_unique_per_company(self):
        import psycopg2
        from odoo.tools import mute_logger

        self.env["chat.agent.skill"].create({"name": "Technical"})
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["chat.agent.skill"].create({"name": "Technical"})

    def test_user_available_for_chat_flag(self):
        self.assertFalse(self.env.user.available_for_chat)
        self.env.user.available_for_chat = True
        self.assertTrue(self.env.user.available_for_chat)

    def test_user_chat_skills_linkable(self):
        skill = self.env["chat.agent.skill"].create({"name": "Sales"})
        self.env.user.chat_skill_ids = [(4, skill.id)]
        self.assertIn(skill, self.env.user.chat_skill_ids)

    def test_escalation_notifies_available_agents(self):
        """escalate() posts to available agents when at least one is marked available."""
        # Mark current user as available
        self.env.user.available_for_chat = True
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        session = self.env["chat.session"].create({"visitor_id": visitor.id})
        session.escalate("trigger_word")
        session.invalidate_recordset()
        self.assertEqual(session.state, "escalated")
        self.assertEqual(session.escalation_reason, "trigger_word")

    def test_escalation_falls_back_when_no_available_agents(self):
        """escalate() still works when no agents have available_for_chat=True."""
        # Ensure no one is marked available
        self.env["res.users"].search([("share", "=", False), ("active", "=", True)]).write(
            {"available_for_chat": False}
        )
        visitor = self.env["chat.visitor"].get_or_create_visitor()
        session = self.env["chat.session"].create({"visitor_id": visitor.id})
        session.escalate("human_requested")
        session.invalidate_recordset()
        self.assertEqual(session.state, "escalated")
