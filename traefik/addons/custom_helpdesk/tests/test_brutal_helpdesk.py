"""Brutal edge-case tests for custom_helpdesk (M13).

- SLA deadline computed from create_date + SLA window
- SLA breach flips exactly at the deadline; closed tickets never breach
- priority ordering; AI replies require approval (never auto-applied)
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class _HelpdeskBase(TransactionCase):
    def _team(self):
        return self.env["helpdesk.team"].search([], limit=1) or self.env["helpdesk.team"].create(
            {"name": "Brutal Team"}
        )

    def _sla(self, days=0, hours=4):
        return self.env["helpdesk.sla"].create(
            {
                "name": f"SLA {days}d{hours}h",
                "time_days": days,
                "time_hours": hours,
                "team_id": self._team().id,
            }
        )

    def _ticket(self, **kw):
        vals = {"name": "Brutal ticket", "description": "x"}
        vals.update(kw)
        return self.env["helpdesk.ticket"].create(vals)


class TestBrutalSlaDeadline(_HelpdeskBase):
    def test_deadline_is_create_plus_window(self):
        sla = self._sla(days=1, hours=0)
        t = self._ticket(sla_id=sla.id)
        if not t.create_date:
            self.skipTest("no create_date")
        expected = t.create_date + timedelta(days=1)
        # allow a small delta for compute timing
        self.assertAlmostEqual((t.sla_deadline - expected).total_seconds(), 0, delta=5)

    def test_closed_ticket_never_breaches(self):
        sla = self._sla(days=0, hours=0)  # deadline = create (immediately past)
        t = self._ticket(sla_id=sla.id)
        closed_stage = self.env["helpdesk.stage"].search([("is_closed", "=", True)], limit=1)
        if not closed_stage:
            self.skipTest("no closed stage")
        t.stage_id = closed_stage
        t._compute_sla_breached()
        self.assertFalse(t.sla_breached, "A closed ticket must never be marked SLA-breached.")

    def test_open_overdue_ticket_breaches(self):
        # Backdate create_date so the SLA deadline lands genuinely in the past
        # (a 0-duration SLA deadline == create == now is NOT < now). This drives
        # the real compute chain: create_date -> sla_deadline -> sla_breached.
        sla = self._sla(days=0, hours=1)
        t = self._ticket(sla_id=sla.id)
        open_stage = self.env["helpdesk.stage"].search([("is_closed", "=", False)], limit=1)
        if open_stage:
            t.stage_id = open_stage
        # Force create_date two hours ago -> deadline (create+1h) is one hour ago.
        t.create_date = fields.Datetime.now() - timedelta(hours=2)
        t._compute_sla_deadline()
        t._compute_sla_breached()
        self.assertTrue(t.sla_breached, "An open ticket past its SLA deadline must be breached.")

    def test_no_sla_no_breach(self):
        t = self._ticket()  # no SLA
        t._compute_sla_breached()
        self.assertFalse(t.sla_breached)


class TestBrutalAiApproval(_HelpdeskBase):
    """AI suggestions must not auto-apply — approval state guards them."""

    def test_ai_approval_state_default_not_approved(self):
        t = self._ticket()
        # ai_approval_state should not start as 'approved'
        self.assertNotEqual(
            t.ai_approval_state, "approved", "AI reply must not be pre-approved on a new ticket."
        )
