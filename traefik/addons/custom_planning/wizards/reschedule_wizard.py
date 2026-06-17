"""Reschedule wizard — change job datetime, record reason, optionally notify customer."""

from odoo import api, fields, models
from odoo.exceptions import UserError


class PlanningRescheduleWizard(models.TransientModel):
    _name = "planning.reschedule.wizard"
    _description = "Reschedule Planning Job"

    job_id = fields.Many2one("platform.planning.job", "Job", required=True, readonly=True)
    current_start = fields.Datetime(
        related="job_id.start_datetime", string="Current Start", readonly=True
    )
    current_end = fields.Datetime(
        related="job_id.end_datetime", string="Current End", readonly=True
    )

    new_start_datetime = fields.Datetime("New Start", required=True)
    new_end_datetime = fields.Datetime("New End", required=True)
    reason = fields.Text("Reason for Reschedule")
    notify_customer = fields.Boolean(
        "Notify Customer",
        default=True,
        help="Post a chatter message to the customer about the new date/time.",
    )

    @api.onchange("new_start_datetime", "new_end_datetime")
    def _onchange_validate_dates(self):
        if self.new_start_datetime and self.new_end_datetime:
            if self.new_end_datetime <= self.new_start_datetime:
                return {
                    "warning": {
                        "title": "Invalid dates",
                        "message": "End must be after start.",
                    }
                }

    def action_confirm_reschedule(self):
        """Apply new dates, log chatter, optionally notify customer."""
        self.ensure_one()
        job = self.job_id

        if job.state in ("completed", "cancelled"):
            raise UserError("Cannot reschedule a completed or cancelled job.")
        if self.new_end_datetime <= self.new_start_datetime:
            raise UserError("New end datetime must be after new start datetime.")

        old_start = job.start_datetime
        old_end = job.end_datetime

        job.write(
            {
                "start_datetime": self.new_start_datetime,
                "end_datetime": self.new_end_datetime,
                "state": "scheduled",  # reschedule drops back to scheduled for re-confirmation
                # Re-arm the reminder: a reminder sent for the OLD time is no longer
                # valid, so clear the flag and let the cron send a fresh reminder for
                # the NEW slot. Without this, a rescheduled job is never re-reminded.
                "reminder_sent": False,
                "reminder_sent_date": False,
            }
        )

        reason_note = f"<br/>Reason: {self.reason}" if self.reason else ""
        chatter_body = (
            f"<b>Job Rescheduled</b><br/>"
            f"Old: {old_start.strftime('%d %b %Y %H:%M') if old_start else '—'} → "
            f"{old_end.strftime('%d %b %Y %H:%M') if old_end else '—'}<br/>"
            f"New: {self.new_start_datetime.strftime('%d %b %Y %H:%M')} → "
            f"{self.new_end_datetime.strftime('%d %b %Y %H:%M')}"
            f"{reason_note}"
        )
        job.message_post(
            body=chatter_body,
            subtype_id=self.env.ref("mail.mt_comment").id,
        )

        if self.notify_customer and job.partner_id:
            job.message_post(
                body=(
                    f"<b>Your appointment has been rescheduled</b><br/>"
                    f"Dear {job.partner_id.name},<br/><br/>"
                    f"Your appointment <b>{job.name}</b> has been rescheduled to:<br/>"
                    f"<b>{self.new_start_datetime.strftime('%d %b %Y %H:%M')}</b><br/>"
                    f"Location: {job.location or 'See contact for details'}"
                    f"{reason_note}<br/><br/>"
                    f"Please contact us if you have questions."
                ),
                subtype_id=self.env.ref("mail.mt_comment").id,
                partner_ids=job.partner_id.ids,
            )

        return {"type": "ir.actions.act_window_close"}
