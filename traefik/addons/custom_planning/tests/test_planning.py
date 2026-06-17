"""Tests for M6 — planning jobs, state machine, sale order linkage, reminders,
reschedule wizard, auto-creation from quote, reminder cron."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

# ── Core job lifecycle ─────────────────────────────────────────────────────────


class TestPlanningJob(TransactionCase):
    """Tests for platform.planning.job model."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create(
            {"name": "Planning Customer", "email": "plan@customer.com"}
        )

    def _make_job(self, **kwargs):
        vals = {
            "name": "Test Job",
            "job_type": "appointment",
            "start_datetime": self.now + timedelta(hours=2),
            "end_datetime": self.now + timedelta(hours=3),
            "partner_id": self.partner.id,
        }
        vals.update(kwargs)
        return self.env["platform.planning.job"].create(vals)

    def test_create_job_draft(self):
        job = self._make_job()
        self.assertEqual(job.state, "draft")

    def test_duration_computed(self):
        job = self._make_job(
            start_datetime=self.now,
            end_datetime=self.now + timedelta(hours=2.5),
        )
        self.assertAlmostEqual(job.duration_hours, 2.5, places=1)

    def test_state_machine_full_flow(self):
        """draft → scheduled → confirmed → in_progress → completed."""
        job = self._make_job()
        job.action_schedule()
        self.assertEqual(job.state, "scheduled")
        job.action_confirm()
        self.assertEqual(job.state, "confirmed")
        job.action_start()
        self.assertEqual(job.state, "in_progress")
        job.action_complete()
        self.assertEqual(job.state, "completed")

    def test_cancel(self):
        job = self._make_job()
        job.action_confirm()
        job.action_cancel()
        self.assertEqual(job.state, "cancelled")

    def test_complete_requires_sign_off(self):
        job = self._make_job(customer_sign_off_required=True)
        job.action_confirm()
        job.action_start()
        with self.assertRaises(UserError):
            job.action_complete()
        job.action_customer_sign_off()
        job.action_complete()
        self.assertEqual(job.state, "completed")
        self.assertTrue(job.customer_signed_off)

    def test_send_reminder_sets_flag(self):
        job = self._make_job()
        job.action_send_reminder()
        self.assertTrue(job.reminder_sent)
        self.assertTrue(job.reminder_sent_date)

    def test_confirm_sends_customer_confirmation(self):
        job = self._make_job(send_customer_confirmation=True)
        job.action_confirm()
        self.assertTrue(job.customer_confirmation_sent)

    def test_sale_order_linkage(self):
        so = self.env["sale.order"].create({"partner_id": self.partner.id})
        job = self._make_job(sale_order_id=so.id)
        self.assertIn(job, so.planning_job_ids)
        self.assertEqual(so.planning_job_count, 1)

    def test_reschedule_opens_wizard(self):
        """action_reschedule now opens the reschedule wizard (not raw form)."""
        job = self._make_job()
        result = job.action_reschedule()
        self.assertEqual(result.get("type"), "ir.actions.act_window")
        self.assertEqual(result.get("res_model"), "planning.reschedule.wizard")
        self.assertEqual(result.get("target"), "new")
        # context pre-fills the job
        self.assertEqual(result["context"]["default_job_id"], job.id)


# ── Resource tests ─────────────────────────────────────────────────────────────


class TestPlanningResource(TransactionCase):

    def test_create_resource(self):
        resource = self.env["platform.planning.resource"].create(
            {"name": "Van 1", "resource_type": "vehicle"}
        )
        self.assertEqual(resource.availability_state, "available")
        self.assertEqual(resource.upcoming_job_count, 0)

    def test_resource_linked_to_job(self):
        resource = self.env["platform.planning.resource"].create(
            {"name": "Drill", "resource_type": "equipment"}
        )
        job = self.env["platform.planning.job"].create(
            {
                "name": "Drill job",
                "job_type": "installation",
                "start_datetime": fields.Datetime.now() + timedelta(hours=1),
                "end_datetime": fields.Datetime.now() + timedelta(hours=3),
                "resource_ids": [(4, resource.id)],
            }
        )
        self.assertIn(resource, job.resource_ids)
        self.assertIn(job, resource.job_ids)


# ── Job types ──────────────────────────────────────────────────────────────────


class TestPlanningJobTypes(TransactionCase):

    def test_job_types_seeded(self):
        types = self.env["platform.planning.job.type"].search([])
        codes = set(types.mapped("code"))
        expected = {
            "appointment",
            "installation",
            "rental_pickup",
            "rental_return",
            "sales_call",
            "support_callback",
            "internal_task",
            "hr_meeting",
        }
        self.assertEqual(codes, expected)

    def test_installation_requires_sign_off(self):
        install = self.env["platform.planning.job.type"].search(
            [("code", "=", "installation")], limit=1
        )
        self.assertTrue(install.requires_customer_sign_off)

    def test_appointment_no_sign_off(self):
        apt = self.env["platform.planning.job.type"].search([("code", "=", "appointment")], limit=1)
        self.assertFalse(apt.requires_customer_sign_off)


# ── Reschedule wizard ──────────────────────────────────────────────────────────


class TestRescheduleWizard(TransactionCase):
    """Tests for planning.reschedule.wizard."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create(
            {"name": "Reschedule Customer", "email": "rs@customer.com"}
        )

    def _make_job(self, **kwargs):
        vals = {
            "name": "Reschedule Test Job",
            "job_type": "appointment",
            "start_datetime": self.now + timedelta(days=2),
            "end_datetime": self.now + timedelta(days=2, hours=1),
            "partner_id": self.partner.id,
            "state": "confirmed",
        }
        vals.update(kwargs)
        return self.env["platform.planning.job"].create(vals)

    def test_reschedule_rearms_reminder(self):
        """A job whose reminder was already sent must have it re-armed on
        reschedule, so the cron sends a fresh reminder for the NEW time.
        (Test-gate: reschedule + reminder scheduling.)"""
        job = self._make_job(reminder_sent=True, reminder_sent_date=self.now)
        self.assertTrue(job.reminder_sent)
        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": self.now + timedelta(days=5),
                "new_end_datetime": self.now + timedelta(days=5, hours=1),
                "notify_customer": False,
            }
        )
        wizard.action_confirm_reschedule()
        self.assertFalse(
            job.reminder_sent, "Reschedule must clear reminder_sent so the cron re-reminds."
        )
        self.assertFalse(job.reminder_sent_date)

    def test_reschedule_changes_datetimes(self):
        """Wizard updates start/end and resets state to scheduled."""
        job = self._make_job()
        new_start = self.now + timedelta(days=5)
        new_end = self.now + timedelta(days=5, hours=2)

        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": new_start,
                "new_end_datetime": new_end,
                "reason": "Customer requested later date",
                "notify_customer": False,
            }
        )
        wizard.action_confirm_reschedule()

        self.assertEqual(job.start_datetime, new_start)
        self.assertEqual(job.end_datetime, new_end)
        self.assertEqual(job.state, "scheduled")

    def test_reschedule_logs_chatter_message(self):
        """Rescheduling posts a message to the job chatter."""
        job = self._make_job()
        msg_count_before = len(job.message_ids)

        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": self.now + timedelta(days=7),
                "new_end_datetime": self.now + timedelta(days=7, hours=1),
                "notify_customer": False,
            }
        )
        wizard.action_confirm_reschedule()

        self.assertGreater(len(job.message_ids), msg_count_before)

    def test_reschedule_notifies_customer_when_enabled(self):
        """When notify_customer=True, customer receives a chatter message."""
        job = self._make_job()

        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": self.now + timedelta(days=6),
                "new_end_datetime": self.now + timedelta(days=6, hours=1),
                "notify_customer": True,
            }
        )
        wizard.action_confirm_reschedule()

        # Customer partner should appear as recipient in at least one message
        all_partners = set()
        for msg in job.message_ids:
            all_partners |= set(msg.partner_ids.ids)
        self.assertIn(self.partner.id, all_partners)

    def test_reschedule_raises_for_completed_job(self):
        """Cannot reschedule a completed job."""
        job = self._make_job(state="completed")
        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": self.now + timedelta(days=3),
                "new_end_datetime": self.now + timedelta(days=3, hours=1),
                "notify_customer": False,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_confirm_reschedule()

    def test_reschedule_raises_for_invalid_dates(self):
        """New end must be after new start."""
        job = self._make_job()
        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": self.now + timedelta(days=3, hours=2),
                "new_end_datetime": self.now + timedelta(days=3),  # before start
                "notify_customer": False,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_confirm_reschedule()

    def test_reschedule_includes_reason_in_message(self):
        """Reason text appears in the chatter message body."""
        job = self._make_job()
        wizard = self.env["planning.reschedule.wizard"].create(
            {
                "job_id": job.id,
                "new_start_datetime": self.now + timedelta(days=4),
                "new_end_datetime": self.now + timedelta(days=4, hours=1),
                "reason": "Urgent schedule conflict",
                "notify_customer": False,
            }
        )
        wizard.action_confirm_reschedule()

        bodies = " ".join(msg.body or "" for msg in job.message_ids)
        self.assertIn("Urgent schedule conflict", bodies)


# ── Auto-creation from quote ───────────────────────────────────────────────────


class TestAutoCreateFromQuote(TransactionCase):
    """Tests for auto-creation of planning job when a service quote is confirmed."""

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Service Customer"})
        self.service_product = self.env["product.product"].create(
            {"name": "Installation Service", "type": "service"}
        )
        self.physical_product = self.env["product.product"].create(
            {"name": "Physical Widget", "type": "consu"}
        )

    def _make_so(self, product):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )

    def test_confirm_service_so_auto_creates_job(self):
        """Confirming a service-product SO auto-creates a draft planning job."""
        so = self._make_so(self.service_product)
        self.assertEqual(len(so.planning_job_ids), 0)
        so.action_confirm()
        self.assertEqual(so.state, "sale")
        self.assertEqual(len(so.planning_job_ids), 1)
        job = so.planning_job_ids[0]
        self.assertEqual(job.state, "draft")
        self.assertEqual(job.job_type, "installation")
        self.assertEqual(job.sale_order_id, so)
        self.assertEqual(job.partner_id, so.partner_id)

    def test_confirm_physical_so_no_auto_job(self):
        """Confirming a physical-product-only SO does NOT auto-create a planning job."""
        so = self._make_so(self.physical_product)
        so.action_confirm()
        self.assertEqual(so.state, "sale")
        self.assertEqual(len(so.planning_job_ids), 0)

    def test_confirm_so_with_existing_jobs_no_duplicate(self):
        """If the SO already has a planning job, confirming does not create another."""
        so = self._make_so(self.service_product)
        # Manually add a job before confirming
        self.env["platform.planning.job"].create(
            {
                "name": "Pre-existing job",
                "job_type": "appointment",
                "sale_order_id": so.id,
                "partner_id": self.partner.id,
                "start_datetime": fields.Datetime.now() + timedelta(hours=1),
                "end_datetime": fields.Datetime.now() + timedelta(hours=2),
            }
        )
        so.action_confirm()
        # Should still have exactly 1 job (the pre-existing one)
        self.assertEqual(len(so.planning_job_ids), 1)

    def test_auto_job_linked_to_so_partner(self):
        """Auto-created job inherits the SO partner."""
        so = self._make_so(self.service_product)
        so.action_confirm()
        if so.planning_job_ids:
            self.assertEqual(so.planning_job_ids[0].partner_id, self.partner)


# ── Reminder cron ──────────────────────────────────────────────────────────────


class TestReminderCron(TransactionCase):
    """Tests for _cron_send_reminders."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create(
            {"name": "Reminder Customer", "email": "remind@customer.com"}
        )

    def _make_job(self, **kwargs):
        vals = {
            "name": "Cron Test Job",
            "job_type": "appointment",
            "start_datetime": self.now + timedelta(hours=12),
            "end_datetime": self.now + timedelta(hours=13),
            "partner_id": self.partner.id,
            "state": "confirmed",
            "reminder_sent": False,
        }
        vals.update(kwargs)
        return self.env["platform.planning.job"].create(vals)

    def test_cron_sends_reminder_for_due_job(self):
        """Cron sends reminder for confirmed job starting within 24 hours."""
        job = self._make_job()
        self.assertFalse(job.reminder_sent)

        self.env["platform.planning.job"]._cron_send_reminders()

        self.assertTrue(job.reminder_sent)
        self.assertTrue(job.reminder_sent_date)

    def test_cron_skips_already_reminded_job(self):
        """Cron does not re-send reminder for a job already marked as reminded."""
        job = self._make_job(reminder_sent=True)
        # Mark the timestamp before cron
        original_date = job.reminder_sent_date

        self.env["platform.planning.job"]._cron_send_reminders()

        # reminder_sent_date should not have changed (no new reminder sent)
        self.assertEqual(job.reminder_sent_date, original_date)

    def test_cron_skips_far_future_job(self):
        """Cron does not send reminder for job starting more than 24h away."""
        job = self._make_job(
            start_datetime=self.now + timedelta(days=5),
            end_datetime=self.now + timedelta(days=5, hours=1),
        )
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertFalse(job.reminder_sent)

    def test_cron_skips_cancelled_job(self):
        """Cron does not send reminder for cancelled jobs."""
        job = self._make_job(state="cancelled")
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertFalse(job.reminder_sent)

    def test_cron_skips_job_without_partner(self):
        """Cron skips jobs with no customer partner."""
        job = self._make_job(partner_id=False)
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertFalse(job.reminder_sent)


# ── Quote-to-job E2E ───────────────────────────────────────────────────────────


class TestQuoteToJobE2E(TransactionCase):
    """End-to-end: quote confirmed → planning job created → full lifecycle → completed."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create(
            {"name": "E2E Customer", "email": "e2e@customer.com"}
        )
        self.service_product = self.env["product.product"].create(
            {"name": "Installation Service", "type": "service"}
        )

    def _make_quote(self):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.service_product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 500.0,
                        },
                    )
                ],
            }
        )

    def _make_job(self, so, job_type="installation"):
        return self.env["platform.planning.job"].create(
            {
                "name": f"Job for {so.name}",
                "job_type": job_type,
                "start_datetime": self.now + timedelta(days=1),
                "end_datetime": self.now + timedelta(days=1, hours=2),
                "partner_id": self.partner.id,
                "sale_order_id": so.id,
                "customer_sign_off_required": True,
                "send_customer_confirmation": False,
            }
        )

    def test_quote_confirm_auto_creates_job(self):
        """Confirming a service SO auto-creates a draft planning job."""
        so = self._make_quote()
        so.action_confirm()
        self.assertEqual(so.state, "sale")
        self.assertGreaterEqual(so.planning_job_count, 1)
        self.assertEqual(so.planning_job_ids[0].state, "draft")

    def test_quote_confirm_then_manual_job_linked(self):
        """Manually creating a job and linking to a confirmed SO works."""
        so = self._make_quote()
        so.action_confirm()

        job = self._make_job(so)
        self.assertIn(job, so.planning_job_ids)
        self.assertGreater(so.planning_job_count, 0)
        self.assertEqual(job.sale_order_id, so)

    def test_full_e2e_quote_to_completed_job(self):
        """Full path: draft → confirm → job → scheduled → confirmed → sign_off → completed."""
        so = self._make_quote()
        so.action_confirm()
        self.assertEqual(so.state, "sale")

        # Use auto-created or manually create
        if not so.planning_job_ids:
            job = self._make_job(so)
        else:
            job = so.planning_job_ids[0]
            # Set sign-off required for E2E test
            job.write({"customer_sign_off_required": True})

        job.action_schedule()
        self.assertEqual(job.state, "scheduled")

        job.action_confirm()
        self.assertEqual(job.state, "confirmed")

        job.action_start()
        self.assertEqual(job.state, "in_progress")

        with self.assertRaises(UserError):
            job.action_complete()

        job.action_customer_sign_off()
        self.assertTrue(job.customer_signed_off)

        job.action_complete()
        self.assertEqual(job.state, "completed")

    def test_view_planning_jobs_action_scoped_to_so(self):
        so = self._make_quote()
        so.action_confirm()
        action = so.action_view_planning_jobs()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertIn(("sale_order_id", "=", so.id), action["domain"])

    def test_cancelled_job_does_not_affect_so(self):
        so = self._make_quote()
        so.action_confirm()
        job = self._make_job(so)
        job.action_confirm()
        job.action_cancel()
        self.assertEqual(job.state, "cancelled")
        self.assertIn(job, so.planning_job_ids)
        self.assertEqual(so.state, "sale")

    def test_multiple_jobs_per_quote(self):
        so = self._make_quote()
        so.action_confirm()
        # May already have 1 auto-created job
        initial_count = so.planning_job_count
        job1 = self._make_job(so, job_type="rental_pickup")
        job2 = self._make_job(so, job_type="rental_return")
        self.assertEqual(so.planning_job_count, initial_count + 2)
        self.assertIn(job1, so.planning_job_ids)
        self.assertIn(job2, so.planning_job_ids)
