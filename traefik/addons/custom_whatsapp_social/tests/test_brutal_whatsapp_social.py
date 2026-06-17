"""Brutal edge-case tests for custom_whatsapp_social (M14).

Safety/compliance invariants:
  - WhatsApp: cannot send without approval; cannot cold-send without opt-in;
    reply to inbound (service window) is allowed
  - Social post: cannot publish/schedule without approval; scheduled-post state
    machine transitions; mock provider only (no live API)
"""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class _WaBase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.provider = self.env["whatsapp.provider"].search(
            [("provider", "=", "mock")], limit=1
        ) or self.env["whatsapp.provider"].create({"name": "Mock", "provider": "mock"})

    def _msg(self, direction="inbound", **kw):
        vals = {
            "provider_id": self.provider.id,
            "direction": direction,
            "from_number": "+31600000001",
            "body": "Hello",
            "state": "received",
        }
        vals.update(kw)
        return self.env["whatsapp.message"].create(vals)


class TestBrutalWhatsappSendGates(_WaBase):
    """Approval AND opt-in/consent gating on send."""

    def test_cannot_send_without_approval(self):
        msg = self._msg(ai_draft="Hi", ai_approval_state="pending")
        with self.assertRaises(UserError):
            msg.action_approve_and_send()

    def test_reply_to_inbound_allowed_without_optin(self):
        # Inbound message = customer-service window; reply allowed without opt-in.
        msg = self._msg(
            direction="inbound", ai_draft="Thanks!", ai_approval_state="approved", opt_in=False
        )
        msg.action_approve_and_send()
        self.assertEqual(msg.state, "sent")

    def test_cold_outbound_without_optin_blocked(self):
        # Outbound, not opted in, not a reply -> must be blocked (WA policy).
        msg = self._msg(
            direction="outbound", ai_draft="Promo!", ai_approval_state="approved", opt_in=False
        )
        with self.assertRaises(UserError):
            msg.action_approve_and_send()

    def test_outbound_with_optin_allowed(self):
        msg = self._msg(
            direction="outbound", ai_draft="Update", ai_approval_state="approved", opt_in=True
        )
        msg.action_approve_and_send()
        self.assertEqual(msg.state, "sent")

    def test_opt_in_recorded(self):
        msg = self._msg()
        self.assertFalse(msg.opt_in)
        msg.action_record_opt_in()
        self.assertTrue(msg.opt_in)
        self.assertTrue(msg.opt_in_date)

    def test_provider_defaults_to_mock(self):
        # Sandbox/mock only — no live sending wired by default.
        self.assertEqual(self.provider.provider, "mock")


class TestBrutalSocialPostStateMachine(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["social.account"].search(
            [("platform", "=", "mock")], limit=1
        ) or self.env["social.account"].create({"name": "Mock", "platform": "mock"})

    def _post(self, **kw):
        vals = {
            "name": "P",
            "body": "Body text",
            "account_ids": [(4, self.account.id)] if self.account else [],
        }
        vals.update(kw)
        return self.env["social.post"].create(vals)

    def test_cannot_publish_unapproved(self):
        post = self._post(state="draft")
        with self.assertRaises(UserError):
            post.action_publish_now()

    def test_cannot_schedule_unapproved(self):
        post = self._post(state="draft", scheduled_date=fields.Datetime.now())
        with self.assertRaises(UserError):
            post.action_schedule()

    def test_cannot_schedule_without_date(self):
        post = self._post(state="approved")
        with self.assertRaises(UserError):
            post.action_schedule()

    def test_approved_post_can_schedule(self):
        post = self._post(
            state="approved",
            scheduled_date=fields.Datetime.now() + __import__("datetime").timedelta(days=1),
        )
        post.action_schedule()
        self.assertEqual(post.state, "scheduled")

    def test_approved_post_can_publish(self):
        post = self._post(state="approved")
        post.action_publish_now()
        self.assertEqual(post.state, "published")

    def test_scheduled_post_can_publish(self):
        post = self._post(
            state="approved",
            scheduled_date=fields.Datetime.now() + __import__("datetime").timedelta(days=1),
        )
        post.action_schedule()
        post.action_publish_now()
        self.assertEqual(post.state, "published")

    def test_reject_returns_to_draft(self):
        post = self._post(state="pending_approval")
        post.action_reject()
        self.assertEqual(post.state, "draft")
