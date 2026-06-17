"""Sick leave reporting — privacy-safe, no unnecessary medical data stored."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrSickLeave(models.Model):
    _name = "hr.sick.leave"
    _description = "Sick Leave Report"
    _inherit = ["mail.thread"]
    _order = "start_date desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", related="employee_id.company_id", store=True)
    manager_id = fields.Many2one(
        "hr.employee", related="employee_id.parent_id", string="Manager", store=True
    )

    # ── Dates (no medical data) ───────────────────────────────────────────────
    start_date = fields.Date("Start Date", required=True, tracking=True)
    expected_end_date = fields.Date("Expected End Date", tracking=True)
    actual_end_date = fields.Date("Actual Return Date", readonly=True)
    duration_days = fields.Integer("Duration (days)", compute="_compute_duration", store=True)

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ("reported", "Reported"),
            ("in_progress", "In Progress"),
            ("partial_recovery", "Partial Recovery"),
            ("recovered", "Recovered"),
            ("reintegration", "Reintegration"),
            ("closed", "Closed"),
        ],
        default="reported",
        tracking=True,
    )

    # ── Privacy-safe fields ───────────────────────────────────────────────────
    # We store ONLY administrative data — no diagnosis, no medical details
    notes = fields.Text(
        "Administrative Notes",
        help="Administrative notes only. Do NOT store diagnoses, symptoms, or medical information.",
    )
    has_doctor_certificate = fields.Boolean(
        "Doctor Certificate Provided",
        help="Check only if a certificate was provided. Do not store the certificate content.",
    )

    # ── Notifications sent ────────────────────────────────────────────────────
    manager_notified = fields.Boolean("Manager Notified", default=False, readonly=True)
    hr_notified = fields.Boolean("HR Notified", default=False, readonly=True)

    @api.depends("start_date", "actual_end_date", "expected_end_date")
    def _compute_duration(self):
        for rec in self:
            end = rec.actual_end_date or rec.expected_end_date
            if rec.start_date and end:
                rec.duration_days = (end - rec.start_date).days + 1
            else:
                rec.duration_days = 0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._notify_manager_and_hr()
        return records

    def _notify_manager_and_hr(self):
        """Notify manager and HR via chatter — no medical details."""
        self.ensure_one()
        employee = self.employee_id
        msg = (
            f"<b>Sick Leave Reported</b><br/>"
            f"Employee: {employee.name}<br/>"
            f"Start date: {self.start_date}<br/>"
            f"Expected return: {self.expected_end_date or 'Unknown'}<br/><br/>"
            f"<em>No medical information is shared. "
            f"Please contact HR for any urgent questions.</em>"
        )

        # Notify manager
        if employee.parent_id and employee.parent_id.user_id:
            self.message_post(
                body=msg,
                partner_ids=[employee.parent_id.user_id.partner_id.id],
            )
            self.manager_notified = True

        # Notify HR
        hr_group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
        if hr_group:
            hr_partners = hr_group.user_ids.mapped("partner_id").ids
            if hr_partners:
                self.message_post(body=msg, partner_ids=hr_partners[:5])
                self.hr_notified = True

    def action_recovery(self):
        """Employee has recovered — record return date."""
        self.write(
            {
                "state": "recovered",
                "actual_end_date": fields.Date.today(),
            }
        )

    def action_partial_recovery(self):
        self.write({"state": "partial_recovery"})

    def action_reintegration(self):
        self.write({"state": "reintegration"})

    def action_close(self):
        self.write({"state": "closed"})

    @api.constrains("start_date", "expected_end_date")
    def _check_start_date_expected_end_date_order(self):
        for rec in self:
            if rec.start_date and rec.expected_end_date and rec.expected_end_date < rec.start_date:
                raise ValidationError("Expected end date must be after the start date.")
