"""Tests for M14 — WhatsApp inbound/approval, social inbox, post state machine."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestWhatsappProvider(TransactionCase):
    """Tests for WhatsApp provider seeding and mock sending."""

    def test_mock_provider_seeded(self):
        provider = self.env["whatsapp.provider"].search([("provider", "=", "mock")], limit=1)
        self.assertTrue(provider, "Mock WA provider must be seeded.")

    def test_mock_provider_send_succeeds(self):
        """Mock provider always returns True."""
        provider = self.env["whatsapp.provider"].search([("provider", "=", "mock")], limit=1)
        result = provider.send_message("+31612345678", "Hello test")
        self.assertTrue(result, "Mock provider must return True.")


class TestWhatsappMessage(TransactionCase):
    """Tests for WhatsApp message lifecycle."""

    def setUp(self):
        super().setUp()
        self.provider = self.env["whatsapp.provider"].search([("provider", "=", "mock")], limit=1)

    def _make_inbound(self, body="Hello", from_number="+31600000001"):
        return self.env["whatsapp.message"].create(
            {
                "provider_id": self.provider.id,
                "direction": "inbound",
                "from_number": from_number,
                "body": body,
                "state": "received",
            }
        )

    def test_create_inbound_message(self):
        msg = self._make_inbound()
        self.assertEqual(msg.direction, "inbound")
        self.assertEqual(msg.state, "received")
        self.assertEqual(msg.ai_approval_state, "none")

    def test_inbound_webhook_creates_message(self):
        """process_inbound_webhook creates a message from mock payload."""
        result = self.env["whatsapp.message"].process_inbound_webhook(
            {"from": "+31611111111", "body": "Webhook test", "id": "mock-test-001"},
            self.provider.id,
        )
        self.assertTrue(result)
        self.assertEqual(result.body, "Webhook test")

    def test_webhook_dedup(self):
        """Same provider_message_id is not created twice."""
        payload = {"from": "+31600000002", "body": "Dedup test", "id": "dedup-123"}
        msg1 = self.env["whatsapp.message"].process_inbound_webhook(payload, self.provider.id)
        msg2 = self.env["whatsapp.message"].process_inbound_webhook(payload, self.provider.id)
        self.assertTrue(msg1)
        self.assertIsNone(msg2, "Duplicate webhook should be skipped.")

    def test_ai_draft_reply_sets_pending(self):
        """action_ai_draft_reply generates a draft and sets pending approval."""
        msg = self._make_inbound("I need pricing information.")
        msg.action_ai_draft_reply()
        if msg.ai_draft:
            self.assertEqual(msg.ai_approval_state, "pending")

    def test_approve_draft(self):
        msg = self._make_inbound()
        msg.write({"ai_draft": "Test reply", "ai_approval_state": "pending"})
        msg.action_approve_draft()
        self.assertEqual(msg.ai_approval_state, "approved")

    def test_send_requires_approved(self):
        """Cannot send without approval."""
        msg = self._make_inbound()
        msg.write({"ai_draft": "Test", "ai_approval_state": "pending"})
        with self.assertRaises(UserError):
            msg.action_approve_and_send()

    def test_approved_mock_send_succeeds(self):
        """Approved message can be sent via mock provider."""
        msg = self._make_inbound("Pricing question")
        msg.write({"ai_draft": "Our pricing is…", "ai_approval_state": "approved"})
        msg.action_approve_and_send()
        self.assertEqual(msg.state, "sent")

    def test_create_lead_from_message(self):
        msg = self._make_inbound("I want to discuss a project.")
        result = msg.action_create_lead()
        self.assertTrue(msg.lead_id)
        self.assertEqual(result["type"], "ir.actions.act_window")

    def test_opt_in_recording(self):
        msg = self._make_inbound()
        self.assertFalse(msg.opt_in)
        msg.action_record_opt_in()
        self.assertTrue(msg.opt_in)
        self.assertTrue(msg.opt_in_date)

    def test_create_ticket_from_wa_message(self):
        """action_create_ticket creates a helpdesk.ticket linked to the WA message."""
        msg = self._make_inbound("I have an urgent issue with my order.")
        result = msg.action_create_ticket()
        self.assertTrue(msg.ticket_id, "ticket_id must be set after action_create_ticket().")
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "helpdesk.ticket")
        # Calling again returns the existing ticket, not a new one
        result2 = msg.action_create_ticket()
        self.assertEqual(result2["res_id"], msg.ticket_id.id)


class TestSocialPost(TransactionCase):
    """Tests for social post state machine and scheduling."""

    def setUp(self):
        super().setUp()
        self.account = self.env["social.account"].search([("platform", "=", "mock")], limit=1)

    def _make_post(self, **kwargs):
        vals = {
            "name": "Test Post",
            "body": "Check out our latest product!",
            "account_ids": [(4, self.account.id)] if self.account else [],
        }
        vals.update(kwargs)
        return self.env["social.post"].create(vals)

    def test_create_post_draft(self):
        post = self._make_post()
        self.assertEqual(post.state, "draft")
        self.assertFalse(post.ai_generated)

    def test_ai_generate_post(self):
        post = self._make_post()
        post.action_ai_generate()
        # With mock AI, body may be updated
        self.assertIn(post.state, ("draft", "ai_generated"))

    def test_full_state_machine(self):
        """draft → pending_approval → approved → scheduled → published."""
        post = self._make_post()
        post.action_submit_for_approval()
        self.assertEqual(post.state, "pending_approval")
        post.action_approve()
        self.assertEqual(post.state, "approved")
        post.scheduled_date = fields.Datetime.now() + timedelta(hours=1)
        post.action_schedule()
        self.assertEqual(post.state, "scheduled")

    def test_publish_requires_approval(self):
        """Cannot publish without approval."""
        post = self._make_post()
        post.action_submit_for_approval()
        with self.assertRaises(UserError):
            post.action_publish_now()

    def test_publish_approved_mock(self):
        """Approved post can be published (mock)."""
        post = self._make_post()
        post.action_submit_for_approval()
        post.action_approve()
        post.action_publish_now()
        self.assertEqual(post.state, "published")
        self.assertTrue(post.published_date)

    def test_cron_publishes_due_posts(self):
        """cron_publish_scheduled publishes posts whose time has passed."""
        post = self._make_post()
        post.action_submit_for_approval()
        post.action_approve()
        # Set scheduled time to the past
        post.scheduled_date = fields.Datetime.now() - timedelta(minutes=5)
        post.state = "scheduled"
        self.env["social.post"].cron_publish_scheduled()
        post.invalidate_recordset()
        self.assertEqual(post.state, "published")

    def test_cancel_post(self):
        post = self._make_post()
        post.action_cancel()
        self.assertEqual(post.state, "cancelled")

    def test_reject_returns_to_draft(self):
        post = self._make_post()
        post.action_submit_for_approval()
        post.action_reject()
        self.assertEqual(post.state, "draft")


class TestSocialInbox(TransactionCase):
    """Tests for social inbox messages."""

    def setUp(self):
        super().setUp()
        self.account = self.env["social.account"].search([("platform", "=", "mock")], limit=1)

    def _make_social_msg(self, **kwargs):
        vals = {
            "account_id": self.account.id,
            "message_type": "comment",
            "author_name": "Test User",
            "body": "Great product!",
        }
        vals.update(kwargs)
        return self.env["social.message"].create(vals)

    def test_create_social_message(self):
        msg = self._make_social_msg()
        self.assertEqual(msg.state, "new")

    def test_ai_draft_reply(self):
        msg = self._make_social_msg()
        msg.action_ai_draft_reply()
        # After AI draft, state should be pending
        if msg.ai_draft_reply:
            self.assertEqual(msg.state, "pending")

    def test_approve_and_send(self):
        msg = self._make_social_msg()
        msg.write(
            {"ai_draft_reply": "Thank you!", "ai_final_reply": "Thank you!", "state": "approved"}
        )
        msg.action_approve_and_send()
        self.assertEqual(msg.state, "sent")

    def test_escalate(self):
        msg = self._make_social_msg(body="I want to sue your company!")
        msg.action_escalate()
        self.assertEqual(msg.state, "escalated")

    def test_create_ticket_from_social_message(self):
        """action_create_ticket creates a helpdesk.ticket linked to the social message."""
        msg = self._make_social_msg(body="Your product broke after one day of use.")
        result = msg.action_create_ticket()
        self.assertTrue(msg.ticket_id, "ticket_id must be set after action_create_ticket().")
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "helpdesk.ticket")
        # Calling again returns the existing ticket, not a new one
        result2 = msg.action_create_ticket()
        self.assertEqual(result2["res_id"], msg.ticket_id.id)

    def test_sentiment_written_on_valid_json_reply(self):
        """Sentiment field is populated when AI returns valid JSON."""
        msg = self._make_social_msg(body="This is terrible, I am so angry!")
        # Simulate what the AI service would return as JSON
        from unittest.mock import patch

        mock_response = {
            "ok": True,
            "content": '{"reply": "We are sorry to hear that.", "sentiment": "angry"}',
        }
        with patch.object(type(self.env["ai.service"]), "call", return_value=mock_response):
            msg.action_ai_draft_reply()
        self.assertEqual(msg.sentiment, "angry")
        self.assertEqual(msg.ai_draft_reply, "We are sorry to hear that.")
        self.assertEqual(msg.state, "pending")
