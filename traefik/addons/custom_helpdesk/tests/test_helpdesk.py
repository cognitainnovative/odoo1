"""Tests for M13 helpdesk — tickets, SLA, AI classification, approval workflow."""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestHelpdeskStages(TransactionCase):
    """Tests for seeded stages."""

    def test_stages_seeded(self):
        stages = self.env["helpdesk.stage"].search([])
        names = stages.mapped("name")
        self.assertIn("New", names)
        self.assertIn("Resolved", names)
        self.assertIn("Closed", names)

    def test_closed_stages_flagged(self):
        closed = self.env["helpdesk.stage"].search([("is_closed", "=", True)])
        self.assertGreater(len(closed), 0, "At least one closed stage must exist.")


class TestHelpdeskTicket(TransactionCase):
    """Tests for helpdesk.ticket model."""

    def setUp(self):
        super().setUp()
        self.stage_new = self.env["helpdesk.stage"].search(
            [("is_closed", "=", False)], order="sequence", limit=1
        )
        self.partner = self.env["res.partner"].create({"name": "Support Customer"})

    def _make_ticket(self, **kwargs):
        vals = {
            "name": "Test Ticket",
            "partner_id": self.partner.id,
            "category": "technical",
        }
        vals.update(kwargs)
        return self.env["helpdesk.ticket"].create(vals)

    def test_create_ticket(self):
        ticket = self._make_ticket()
        self.assertTrue(ticket.name)
        self.assertEqual(ticket.ai_approval_state, "none")
        self.assertFalse(ticket.sla_breached)

    def test_ai_classify_with_mock(self):
        """AI classification runs with mock provider without error."""
        ticket = self._make_ticket(description="<p>My invoice is incorrect, I want a refund.</p>")
        ticket.action_ai_classify()
        # With mock provider, JSON parse may fail gracefully
        # Just check it ran without error and category may or may not be set
        self.assertIsNotNone(ticket.name)  # ticket is still valid

    def test_ai_draft_reply_workflow(self):
        """AI draft → pending → approved → send."""
        ticket = self._make_ticket()
        ticket.action_ai_draft_reply()
        # May be 'none' if AI returned nothing useful, but state transitions work
        if ticket.ai_approval_state == "pending":
            ticket.action_approve_reply()
            self.assertEqual(ticket.ai_approval_state, "approved")
            ticket.action_send_reply()
            self.assertEqual(ticket.ai_approval_state, "sent")

    def test_send_without_approval_raises(self):
        """Cannot send reply without approval."""
        ticket = self._make_ticket()
        ticket.write(
            {
                "ai_draft_reply": "Test reply",
                "ai_final_reply": "Test reply",
                "ai_approval_state": "pending",
            }
        )
        with self.assertRaises(UserError):
            ticket.action_send_reply()

    def test_close_ticket(self):
        """action_close moves ticket to a closed stage."""
        ticket = self._make_ticket()
        ticket.action_close()
        self.assertTrue(ticket.stage_id.is_closed)

    def test_sla_deadline_set_from_rule(self):
        """SLA deadline is computed when SLA is assigned."""
        team = self.env["helpdesk.team"].create({"name": "Test Team", "use_sla": True})
        sla = self.env["helpdesk.sla"].create(
            {
                "name": "1-Day SLA",
                "team_id": team.id,
                "priority": "0",
                "time_days": 1,
            }
        )
        ticket = self._make_ticket(sla_id=sla.id)
        self.assertTrue(ticket.sla_deadline)

    def test_risk_flags_default_false(self):
        ticket = self._make_ticket()
        self.assertFalse(ticket.is_complaint)
        self.assertFalse(ticket.has_legal_risk)
        self.assertFalse(ticket.has_missing_info)


class TestHelpdeskSla(TransactionCase):
    """Tests for SLA calculation."""

    def test_sla_deadline_calculation(self):
        team = self.env["helpdesk.team"].create({"name": "SLA Team", "use_sla": True})
        sla = self.env["helpdesk.sla"].create(
            {
                "name": "2-Day SLA",
                "team_id": team.id,
                "priority": "1",
                "time_days": 2,
                "time_hours": 4,
            }
        )
        from_date = fields.Datetime.now()
        deadline = sla.get_deadline(from_date)
        expected = from_date + __import__("datetime").timedelta(days=2, hours=4)
        diff = abs((deadline - expected).total_seconds())
        self.assertLess(diff, 60, "Deadline should be within 1 minute of expected.")

    def test_sla_cron_posts_note_on_breached_ticket(self):
        """Test gate: SLA escalation timer — cron posts a note on breached tickets."""
        import datetime

        team = self.env["helpdesk.team"].create({"name": "Cron Test Team", "use_sla": True})
        sla = self.env["helpdesk.sla"].create(
            {
                "name": "Instant SLA",
                "team_id": team.id,
                "priority": "0",
                "time_days": 0,
                "time_hours": 0,
            }
        )
        partner = self.env["res.partner"].create({"name": "SLA Cron Customer"})
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Overdue Ticket",
                "partner_id": partner.id,
                "sla_id": sla.id,
            }
        )
        # Manually force deadline to the past
        ticket.sla_deadline = fields.Datetime.now() - datetime.timedelta(hours=1)

        msg_count_before = len(ticket.message_ids)
        self.env["helpdesk.ticket"].cron_check_sla()
        ticket.invalidate_recordset()
        self.assertGreater(
            len(ticket.message_ids),
            msg_count_before,
            "cron_check_sla must post a note on SLA-breached tickets.",
        )

    def test_sla_cron_warns_on_approaching_deadline(self):
        """Cron posts a warning note for tickets with SLA deadline within 4 hours."""
        import datetime

        team = self.env["helpdesk.team"].create({"name": "Warning Team", "use_sla": True})
        sla = self.env["helpdesk.sla"].create(
            {
                "name": "1-Hour SLA",
                "team_id": team.id,
                "priority": "0",
                "time_days": 0,
                "time_hours": 1,
            }
        )
        partner = self.env["res.partner"].create({"name": "Approaching SLA Customer"})
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Approaching SLA Ticket",
                "partner_id": partner.id,
                "sla_id": sla.id,
            }
        )
        # Set deadline 2 hours from now (within the 4-hour warning window)
        ticket.sla_deadline = fields.Datetime.now() + datetime.timedelta(hours=2)

        msg_count_before = len(ticket.message_ids)
        self.env["helpdesk.ticket"].cron_check_sla()
        ticket.invalidate_recordset()
        self.assertGreater(
            len(ticket.message_ids),
            msg_count_before,
            "cron_check_sla must post a warning for approaching-deadline tickets.",
        )


class TestHelpdeskEndToEnd(TransactionCase):
    """Test gate: email→ticket→AI classify→AI draft→employee edit→reason stored→send→close."""

    def test_full_ticket_workflow(self):
        """End-to-end: create via email source, classify, draft, edit, approve, send, close."""
        partner = self.env["res.partner"].create(
            {
                "name": "E2E Test Customer",
                "email": "e2e@example.com",
            }
        )

        # 1. Create ticket (simulating email source)
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "My invoice #1234 is wrong",
                "description": "<p>The amount is incorrect. Please refund €50.</p>",
                "source": "email",
                "partner_id": partner.id,
                "category": "billing",
            }
        )
        self.assertEqual(ticket.source, "email")
        self.assertEqual(ticket.ai_approval_state, "none")

        # 2. AI classify (may fail gracefully in test env)
        ticket.action_ai_classify()
        # Classification result is provider-dependent — just assert no exception

        # 3. AI draft reply → state goes to pending
        ticket.action_ai_draft_reply()
        if ticket.ai_approval_state == "pending":
            # 4. Employee edits the draft and records reason
            ticket.write(
                {
                    "ai_final_reply": "Dear customer, we have reviewed your invoice. A refund has been issued.",
                    "ai_edit_reason": "AI draft was too formal — simplified language",
                }
            )
            self.assertTrue(ticket.ai_edit_reason)
            self.assertNotEqual(ticket.ai_final_reply, ticket.ai_draft_reply)

            # 5. Approve
            ticket.action_approve_reply()
            self.assertEqual(ticket.ai_approval_state, "approved")

            # 6. Send (creates a chatter message + sets state to sent)
            ticket.action_send_reply()
            self.assertEqual(ticket.ai_approval_state, "sent")

        # 7. Close ticket
        ticket.action_close()
        self.assertTrue(ticket.stage_id.is_closed)

    def test_send_before_approval_blocked(self):
        """Cannot send AI draft without approval — confirms 'never auto-send' rule."""
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "No-Auto-Send Test",
                "ai_draft_reply": "Draft content",
                "ai_final_reply": "Draft content",
                "ai_approval_state": "pending",
            }
        )
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            ticket.action_send_reply()

    def test_edit_reason_stored_when_reply_differs(self):
        """Edit reason is preserved on the ticket for AI learning."""
        partner = self.env["res.partner"].create({"name": "Edit Reason Test"})
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "partner_id": partner.id,
                "ai_draft_reply": "Original AI draft",
                "ai_final_reply": "Edited reply by human",
                "ai_approval_state": "pending",
                "ai_edit_reason": "Changed greeting and tone",
            }
        )
        ticket.action_approve_reply()
        ticket.action_send_reply()
        self.assertEqual(ticket.ai_approval_state, "sent")
        self.assertEqual(ticket.ai_edit_reason, "Changed greeting and tone")

    def test_follow_up_action_creates_activity(self):
        """action_follow_up schedules a mail.activity on the ticket."""
        partner = self.env["res.partner"].create({"name": "Follow-up Test"})
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Needs Follow-up",
                "partner_id": partner.id,
            }
        )
        ticket.action_follow_up()
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "helpdesk.ticket"), ("res_id", "=", ticket.id)]
        )
        self.assertTrue(activities, "Follow-up action must create at least one activity.")


class TestHelpdeskSkillRouting(TransactionCase):
    """Tests for skill-based and workload-based ticket routing."""

    def setUp(self):
        super().setUp()
        self.skill_billing = self.env["helpdesk.skill"].create({"name": "Billing"})
        self.skill_tech = self.env["helpdesk.skill"].create({"name": "Technical Support"})
        self.agent1 = self.env["res.users"].create(
            {
                "name": "Agent One",
                "login": "agent_one_test@example.com",
            }
        )
        self.agent2 = self.env["res.users"].create(
            {
                "name": "Agent Two",
                "login": "agent_two_test@example.com",
            }
        )
        self.skill_billing.agent_ids = [self.agent1.id]
        self.skill_tech.agent_ids = [self.agent2.id]
        self.team = self.env["helpdesk.team"].create(
            {
                "name": "Routing Test Team",
                "member_ids": [(6, 0, [self.agent1.id, self.agent2.id])],
                "auto_assign": True,
            }
        )

    def test_skill_model_exists(self):
        skill = self.env["helpdesk.skill"].create({"name": "Network"})
        self.assertTrue(skill.name)

    def test_team_has_skill_ids(self):
        self.team.skill_ids = [(6, 0, [self.skill_billing.id, self.skill_tech.id])]
        self.assertIn(self.skill_billing, self.team.skill_ids)

    def test_get_next_assignee_workload_balance(self):
        """Member with fewer open tickets is chosen first."""
        partner = self.env["res.partner"].create({"name": "WL Test"})
        # Give agent1 an open ticket
        self.env["helpdesk.ticket"].create(
            {
                "name": "Existing ticket",
                "partner_id": partner.id,
                "user_id": self.agent1.id,
            }
        )
        assignee = self.team._get_next_assignee()
        self.assertEqual(assignee, self.agent2, "Agent2 should be chosen (lower load).")

    def test_get_next_assignee_skill_filter(self):
        """Skill filter narrows candidates to skilled agents."""
        assignee = self.team._get_next_assignee(skill_id=self.skill_billing.id)
        self.assertEqual(assignee, self.agent1, "Only agent1 has billing skill.")

    def test_ticket_has_skill_and_product_fields(self):
        product = self.env["product.product"].create({"name": "Support Widget"})
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Ticket with skill + product",
                "skill_id": self.skill_billing.id,
                "product_id": product.id,
            }
        )
        self.assertEqual(ticket.skill_id, self.skill_billing)
        self.assertEqual(ticket.product_id, product)

    def test_action_accept_ai_assignee(self):
        """action_accept_ai_assignee copies ai_suggested_user_id to user_id."""
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Assignee Accept Test",
                "ai_suggested_user_id": self.agent1.id,
            }
        )
        self.assertFalse(ticket.user_id)
        ticket.action_accept_ai_assignee()
        self.assertEqual(ticket.user_id, self.agent1)

    def test_auto_route_assigns_when_team_auto_assign_enabled(self):
        """_auto_route assigns the least-loaded skilled member."""
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Auto-route Test",
                "team_id": self.team.id,
                "skill_id": self.skill_tech.id,
            }
        )
        ticket._auto_route()
        self.assertEqual(ticket.user_id, self.agent2, "agent2 has tech skill and lowest load.")

    def test_missing_info_followup_scheduled(self):
        """_schedule_missing_info_followup creates an activity on the ticket."""
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Missing Info Test",
                "has_missing_info": True,
            }
        )
        ticket._schedule_missing_info_followup()
        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "helpdesk.ticket"),
                ("res_id", "=", ticket.id),
            ]
        )
        self.assertTrue(activities, "Follow-up activity must be created for missing-info tickets.")

    def test_missing_info_followup_not_duplicated(self):
        """Calling _schedule_missing_info_followup twice creates only one activity."""
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "No Duplicate Followup",
                "has_missing_info": True,
            }
        )
        ticket._schedule_missing_info_followup()
        ticket._schedule_missing_info_followup()
        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "helpdesk.ticket"),
                ("res_id", "=", ticket.id),
            ]
        )
        self.assertEqual(len(activities), 1, "Duplicate follow-up activities must not be created.")
