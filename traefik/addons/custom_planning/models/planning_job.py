"""Platform Planning — jobs, appointments, tasks linked to CRM, sales, and HR."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PlanningJob(models.Model):
    _name = "platform.planning.job"
    _description = "Planning Job / Appointment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_datetime, name"
    _rec_name = "name"

    name = fields.Char(required=True, tracking=True)
    job_type = fields.Selection(
        [
            ("appointment", "Appointment"),
            ("installation", "Installation / Service"),
            ("rental_pickup", "Rental Pickup"),
            ("rental_return", "Rental Return"),
            ("sales_call", "Sales / Follow-up Call"),
            ("support_callback", "Support Callback"),
            ("internal_task", "Internal Task"),
            ("hr_meeting", "HR Meeting"),
            ("other", "Other"),
        ],
        string="Type",
        required=True,
        default="appointment",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("confirmed", "Confirmed"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )
    priority = fields.Selection(
        [("0", "Normal"), ("1", "Urgent")],
        default="0",
    )

    # ── Timing ────────────────────────────────────────────────────────────────
    start_datetime = fields.Datetime("Start", required=True, tracking=True)
    end_datetime = fields.Datetime("End", required=True, tracking=True)

    @api.constrains("start_datetime", "end_datetime")
    def _check_start_datetime_end_datetime_order(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime and rec.end_datetime < rec.start_datetime:
                raise ValidationError("End time must be after the start time.")

    duration_hours = fields.Float(
        "Duration (h)", compute="_compute_duration", store=True, readonly=False
    )
    all_day = fields.Boolean("All Day", default=False)

    # ── People & teams ────────────────────────────────────────────────────────
    partner_id = fields.Many2one("res.partner", "Customer / Contact", index=True)
    employee_id = fields.Many2one("hr.employee", "Assigned Employee", index=True)
    team_ids = fields.Many2many(
        "hr.employee", "planning_job_employee_rel", "job_id", "employee_id", "Team Members"
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    # ── Location ──────────────────────────────────────────────────────────────
    location = fields.Char("Location / Address")
    location_notes = fields.Text("Travel / Location Notes")

    # ── Links to other modules ────────────────────────────────────────────────
    sale_order_id = fields.Many2one("sale.order", "Linked Sale Order", ondelete="set null")
    crm_lead_id = fields.Many2one("crm.lead", "Linked Deal / Lead", ondelete="set null")
    invoice_id = fields.Many2one("account.move", "Linked Invoice", ondelete="set null")

    # ── Content ───────────────────────────────────────────────────────────────
    description = fields.Html("Description / Instructions")
    internal_notes = fields.Text("Internal Notes")
    completion_notes = fields.Text("Completion Notes")

    # ── Customer sign-off ─────────────────────────────────────────────────────
    customer_sign_off_required = fields.Boolean("Requires Customer Sign-off", default=False)
    customer_signed_off = fields.Boolean("Customer Signed Off", default=False, readonly=True)
    customer_sign_off_date = fields.Datetime(readonly=True)

    # ── Reminders ─────────────────────────────────────────────────────────────
    reminder_sent = fields.Boolean("Reminder Sent", default=False, readonly=True)
    reminder_sent_date = fields.Datetime(readonly=True)
    send_customer_confirmation = fields.Boolean("Send Confirmation Email", default=True)
    customer_confirmation_sent = fields.Boolean(readonly=True, default=False)

    # ── Resource links ────────────────────────────────────────────────────────
    resource_ids = fields.Many2many(
        "platform.planning.resource",
        "planning_job_resource_rel",
        "job_id",
        "resource_id",
        "Resources",
    )

    @api.depends("start_datetime", "end_datetime")
    def _compute_duration(self):
        for job in self:
            if job.start_datetime and job.end_datetime:
                delta = job.end_datetime - job.start_datetime
                job.duration_hours = delta.total_seconds() / 3600
            else:
                job.duration_hours = 0.0

    # ── State transitions ─────────────────────────────────────────────────────

    def action_schedule(self):
        self.write({"state": "scheduled"})

    def action_confirm(self):
        for job in self:
            job.write({"state": "confirmed"})
            if job.send_customer_confirmation and not job.customer_confirmation_sent:
                job._send_customer_confirmation()

    def action_start(self):
        self.write({"state": "in_progress"})

    def action_complete(self):
        for job in self:
            if job.customer_sign_off_required and not job.customer_signed_off:
                raise UserError("This job requires customer sign-off before it can be completed.")
            job.write({"state": "completed"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_reschedule(self):
        """Open reschedule wizard with pre-filled current dates."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Reschedule Job",
            "res_model": "planning.reschedule.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_job_id": self.id,
                "default_new_start_datetime": self.start_datetime,
                "default_new_end_datetime": self.end_datetime,
            },
        }

    def action_customer_sign_off(self):
        """Record customer sign-off on the job."""
        self.write(
            {
                "customer_signed_off": True,
                "customer_sign_off_date": fields.Datetime.now(),
            }
        )

    def action_send_reminder(self):
        """Send a reminder message to the customer."""
        for job in self:
            if not job.partner_id:
                continue
            job.message_post(
                body=(
                    f"<b>Reminder:</b> You have a scheduled appointment: "
                    f"<b>{job.name}</b> on "
                    f"{job.start_datetime.strftime('%d %b %Y %H:%M') if job.start_datetime else 'TBD'}."
                    f"<br/>Location: {job.location or 'TBD'}"
                ),
                subtype_id=self.env.ref("mail.mt_comment").id,
                partner_ids=job.partner_id.ids,
            )
            job.write({"reminder_sent": True, "reminder_sent_date": fields.Datetime.now()})

    def _send_customer_confirmation(self):
        """Send customer confirmation email (chatter + optional email template)."""
        self.ensure_one()
        if self.partner_id:
            self.message_post(
                body=(
                    f"<b>Appointment Confirmed</b><br/>"
                    f"Dear {self.partner_id.name},<br/><br/>"
                    f"Your appointment <b>{self.name}</b> has been confirmed.<br/>"
                    f"Date: {self.start_datetime.strftime('%d %b %Y %H:%M') if self.start_datetime else 'TBD'}<br/>"
                    f"Location: {self.location or 'See contact for details'}<br/><br/>"
                    f"Please contact us if you need to reschedule."
                ),
                subtype_id=self.env.ref("mail.mt_comment").id,
                partner_ids=self.partner_id.ids,
            )
            self.customer_confirmation_sent = True

    @api.model
    def _cron_send_reminders(self):
        """Daily cron: send reminders for jobs starting within the next 24 hours."""
        from datetime import timedelta

        now = fields.Datetime.now()
        cutoff = now + timedelta(hours=24)
        due_jobs = self.sudo().search(
            [
                ("start_datetime", ">=", now),
                ("start_datetime", "<=", cutoff),
                ("state", "in", ("scheduled", "confirmed")),
                ("reminder_sent", "=", False),
                ("partner_id", "!=", False),
            ]
        )
        for job in due_jobs:
            try:
                job.action_send_reminder()
            except Exception as exc:
                _logger.error("Reminder cron failed for job %s: %s", job.name, exc)
        _logger.info("Planning reminder cron: sent %d reminder(s).", len(due_jobs))

    # ── Completion report ─────────────────────────────────────────────────────

    def action_print_completion_report(self):
        """Print a PDF completion report for this job."""
        return {
            "type": "ir.actions.report",
            "report_type": "qweb-pdf",
            "report_name": "custom_planning.report_job_completion",
            "res_ids": self.ids,
        }


class PlanningJobType(models.Model):
    """Optional: company-specific custom job type definitions (beyond the selection field)."""

    _name = "platform.planning.job.type"
    _description = "Planning Job Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    default_duration_hours = fields.Float("Default Duration (h)", default=1.0)
    requires_customer_sign_off = fields.Boolean(default=False)
    color = fields.Integer("Kanban Color", default=0)
    active = fields.Boolean(default=True)
