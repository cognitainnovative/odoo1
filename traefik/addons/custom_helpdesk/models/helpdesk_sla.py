"""SLA policy model."""

from datetime import timedelta

from odoo import fields, models


class HelpdeskSla(models.Model):
    _name = "helpdesk.sla"
    _description = "SLA Policy"
    _order = "priority desc, name"

    name = fields.Char(required=True)
    team_id = fields.Many2one("helpdesk.team", required=True, ondelete="cascade")
    priority = fields.Selection(
        [("0", "Normal"), ("1", "High"), ("2", "Urgent")],
        default="0",
        required=True,
    )
    time_days = fields.Integer("Days", default=1)
    time_hours = fields.Integer("Hours", default=0)
    active = fields.Boolean(default=True)

    def get_deadline(self, from_date=None):
        """Return the SLA deadline for a ticket created now (or from_date)."""
        from_date = from_date or fields.Datetime.now()
        delta = timedelta(days=self.time_days, hours=self.time_hours)
        return from_date + delta
