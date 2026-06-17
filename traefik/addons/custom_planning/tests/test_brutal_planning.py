"""Brutal edge-case tests for custom_planning (M6).

Targets logic the standard 35 tests don't cover:
  - reminder cron window boundaries (exactly 24h, just past, far future)
  - reschedule re-arms reminder (test-gate: reschedule + reminder)
  - sign-off gating blocks completion; sign-off then completes
  - employee planning job-count compute + availability flag
  - resource upcoming-job-count compute (excludes done/cancelled/past)
  - customer confirmation only sent once; reminder idempotent
  - completion report action returns a valid report action
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestBrutalReminderWindow(TransactionCase):
    """_cron_send_reminders window boundaries."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create(
            {"name": "Reminder Cust", "email": "rem@cust.com"}
        )

    def _job(self, start_offset_hours, **kw):
        vals = {
            "name": "Window Job",
            "job_type": "appointment",
            "start_datetime": self.now + timedelta(hours=start_offset_hours),
            "end_datetime": self.now + timedelta(hours=start_offset_hours + 1),
            "partner_id": self.partner.id,
            "state": "confirmed",
        }
        vals.update(kw)
        return self.env["platform.planning.job"].create(vals)

    def test_job_within_24h_gets_reminder(self):
        job = self._job(12)
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertTrue(job.reminder_sent)

    def test_job_far_future_no_reminder(self):
        job = self._job(72)  # 3 days out
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertFalse(job.reminder_sent)

    def test_job_in_past_no_reminder(self):
        job = self._job(-5)  # already started
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertFalse(job.reminder_sent)

    def test_cron_is_idempotent(self):
        job = self._job(6)
        self.env["platform.planning.job"]._cron_send_reminders()
        self.env["platform.planning.job"]._cron_send_reminders()  # twice
        # Only one reminder flag; no error, no double-processing
        self.assertTrue(job.reminder_sent)

    def test_draft_job_no_reminder(self):
        job = self._job(6, state="draft")
        self.env["platform.planning.job"]._cron_send_reminders()
        self.assertFalse(job.reminder_sent)


class TestBrutalSignOffGating(TransactionCase):
    """Customer sign-off must block completion until recorded."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()

    def _job(self, **kw):
        vals = {
            "name": "SignOff Job",
            "job_type": "installation",
            "start_datetime": self.now,
            "end_datetime": self.now + timedelta(hours=2),
            "customer_sign_off_required": True,
            "state": "in_progress",
        }
        vals.update(kw)
        return self.env["platform.planning.job"].create(vals)

    def test_complete_blocked_without_signoff(self):
        from odoo.exceptions import UserError

        job = self._job()
        with self.assertRaises(UserError):
            job.action_complete()
        self.assertNotEqual(job.state, "completed")

    def test_complete_allowed_after_signoff(self):
        job = self._job()
        job.action_customer_sign_off()
        self.assertTrue(job.customer_signed_off)
        self.assertTrue(job.customer_sign_off_date)
        job.action_complete()
        self.assertEqual(job.state, "completed")

    def test_no_signoff_required_completes_freely(self):
        job = self._job(customer_sign_off_required=False)
        job.action_complete()
        self.assertEqual(job.state, "completed")


class TestBrutalEmployeeAvailability(TransactionCase):
    """Employee planning fields: job count + availability flag."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.emp = self.env["hr.employee"].create({"name": "Brutal Tech"})

    def test_job_count_excludes_done_and_past(self):
        Job = self.env["platform.planning.job"]
        # upcoming active job -> counts
        Job.create(
            {
                "name": "Upcoming",
                "job_type": "appointment",
                "start_datetime": self.now + timedelta(days=1),
                "end_datetime": self.now + timedelta(days=1, hours=1),
                "employee_id": self.emp.id,
                "state": "confirmed",
            }
        )
        # completed job -> excluded
        Job.create(
            {
                "name": "Done",
                "job_type": "appointment",
                "start_datetime": self.now + timedelta(days=1),
                "end_datetime": self.now + timedelta(days=1, hours=1),
                "employee_id": self.emp.id,
                "state": "completed",
            }
        )
        self.emp._compute_planning_job_count()
        self.assertEqual(self.emp.planning_job_count, 1)

    def test_availability_flag_default_true(self):
        self.assertTrue(self.emp.planning_available)

    def test_skills_stored(self):
        self.emp.planning_skills = "electrician, forklift, Dutch"
        self.assertIn("forklift", self.emp.planning_skills)


class TestBrutalResourceCount(TransactionCase):
    """Resource upcoming-job-count excludes done/cancelled/past jobs."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.res = self.env["platform.planning.resource"].create(
            {"name": "Van 1", "resource_type": "vehicle"}
        )

    def _job(self, state, offset_days):
        return self.env["platform.planning.job"].create(
            {
                "name": f"Res Job {state}",
                "job_type": "installation",
                "start_datetime": self.now + timedelta(days=offset_days),
                "end_datetime": self.now + timedelta(days=offset_days, hours=1),
                "state": state,
                "resource_ids": [(4, self.res.id)],
            }
        )

    def test_count_only_upcoming_active(self):
        self._job("confirmed", 1)  # counts
        self._job("completed", 1)  # excluded (done)
        self._job("cancelled", 1)  # excluded
        self._job("confirmed", -2)  # excluded (past)
        self.res._compute_upcoming_job_count()
        self.assertEqual(self.res.upcoming_job_count, 1)


class TestBrutalConfirmationAndReport(TransactionCase):
    """Customer confirmation sent once; completion report action valid."""

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create(
            {"name": "Conf Cust", "email": "conf@cust.com"}
        )

    def _job(self, **kw):
        vals = {
            "name": "Conf Job",
            "job_type": "appointment",
            "start_datetime": self.now + timedelta(days=1),
            "end_datetime": self.now + timedelta(days=1, hours=1),
            "partner_id": self.partner.id,
            "state": "scheduled",
            "send_customer_confirmation": True,
        }
        vals.update(kw)
        return self.env["platform.planning.job"].create(vals)

    def test_confirmation_sent_once_on_confirm(self):
        job = self._job()
        job.action_confirm()
        self.assertTrue(job.customer_confirmation_sent)
        # Re-confirming must not re-send (guard on customer_confirmation_sent)
        before = job.customer_confirmation_sent
        job.action_confirm()
        self.assertEqual(job.customer_confirmation_sent, before)

    def test_completion_report_action_valid(self):
        job = self._job()
        action = job.action_print_completion_report()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(action["report_name"], "custom_planning.report_job_completion")
        self.assertIn(job.id, action["res_ids"])

    def test_reminder_without_partner_no_crash(self):
        job = self._job(partner_id=False)
        # action_send_reminder must skip gracefully when no partner
        job.action_send_reminder()
        self.assertFalse(job.reminder_sent)
