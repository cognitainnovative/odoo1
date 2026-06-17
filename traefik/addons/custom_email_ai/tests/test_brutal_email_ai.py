"""Brutal edge-case tests for custom_email_ai (M13).

The single most important invariant: AI replies NEVER auto-send by default.
  - outbox cannot send unless state == approved
  - auto-send is empty/inert unless admin enabled it AND category matches
  - edit_reason is stored when a draft is edited (learning loop)
  - pending outbox state machine transitions
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class _EmailBase(TransactionCase):
    def _mailbox(self, **kw):
        vals = {"name": "Test MB", "email_address": "support@test.local"}
        vals.update(kw)
        return self.env["email.ai.mailbox"].create(vals)

    def _outbox(self, mailbox, **kw):
        vals = {
            "mailbox_id": mailbox.id,
            "to_email": "customer@test.local",
            "subject": "Re: your question",
            "body_draft": "Draft reply text",
            "body_final": "Draft reply text",
        }
        vals.update(kw)
        return self.env["email.ai.outbox"].create(vals)


class TestBrutalNeverAutoSend(_EmailBase):
    """The never-auto-send-by-default safety invariant, probed adversarially."""

    def test_new_outbox_is_pending(self):
        mb = self._mailbox()
        ob = self._outbox(mb)
        self.assertEqual(
            ob.state, "pending", "A new AI draft must start pending, never approved/sent."
        )

    def test_cannot_send_unapproved(self):
        mb = self._mailbox()
        ob = self._outbox(mb)  # pending
        with self.assertRaises(UserError):
            ob.action_send()

    def test_cannot_send_rejected(self):
        mb = self._mailbox()
        ob = self._outbox(mb)
        ob.action_reject()
        with self.assertRaises(UserError):
            ob.action_send()

    def test_auto_send_disabled_by_default(self):
        mb = self._mailbox()
        self.assertFalse(mb.auto_send_enabled)
        self.assertEqual(
            mb.get_auto_send_categories(),
            set(),
            "No categories may auto-send unless admin explicitly enabled it.",
        )

    def test_auto_send_categories_inert_when_disabled(self):
        # Even if categories are listed, disabled flag must make them inert.
        mb = self._mailbox(auto_send_enabled=False, auto_send_categories="general,helpdesk")
        self.assertEqual(
            mb.get_auto_send_categories(),
            set(),
            "Listed categories must have NO effect while auto_send_enabled is False.",
        )

    def test_auto_send_only_for_enabled_categories(self):
        mb = self._mailbox(auto_send_enabled=True, auto_send_categories="general")
        cats = mb.get_auto_send_categories()
        self.assertIn("general", cats)
        self.assertNotIn(
            "invoice", cats, "A category not listed must never auto-send even with auto-send on."
        )


class TestBrutalOutboxStateMachine(_EmailBase):
    def test_approve_sets_approver(self):
        mb = self._mailbox()
        ob = self._outbox(mb)
        ob.action_approve()
        self.assertEqual(ob.state, "approved")
        self.assertEqual(ob.approved_by_id, self.env.user)

    def test_needs_info_state(self):
        mb = self._mailbox()
        ob = self._outbox(mb)
        ob.action_needs_info()
        self.assertEqual(ob.state, "needs_info")
        # still cannot send from needs_info
        with self.assertRaises(UserError):
            ob.action_send()

    def test_edit_reason_persists(self):
        mb = self._mailbox()
        ob = self._outbox(mb, body_final="Edited reply", edit_reason="Fixed tone")
        self.assertEqual(ob.edit_reason, "Fixed tone")
        self.assertNotEqual(ob.body_final, ob.body_draft)
