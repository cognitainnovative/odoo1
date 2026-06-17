"""Planning resources — vehicles, equipment, rooms, etc."""

from odoo import api, fields, models


class PlanningResource(models.Model):
    _name = "platform.planning.resource"
    _description = "Planning Resource"
    _order = "resource_type, name"

    name = fields.Char(required=True)
    resource_type = fields.Selection(
        [
            ("vehicle", "Vehicle"),
            ("equipment", "Equipment"),
            ("room", "Room / Location"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    employee_id = fields.Many2one(
        "hr.employee",
        "Responsible Employee",
        help="Employee who manages or operates this resource.",
    )
    description = fields.Text()
    active = fields.Boolean(default=True)
    color = fields.Integer("Kanban Color", default=0)

    # ── Availability ──────────────────────────────────────────────────────────
    availability_state = fields.Selection(
        [
            ("available", "Available"),
            ("in_use", "In Use"),
            ("maintenance", "Under Maintenance"),
            ("unavailable", "Unavailable"),
        ],
        default="available",
    )

    job_ids = fields.Many2many(
        "platform.planning.job",
        "planning_job_resource_rel",
        "resource_id",
        "job_id",
        "Assigned Jobs",
    )
    upcoming_job_count = fields.Integer(compute="_compute_upcoming_job_count")

    @api.depends("job_ids")
    def _compute_upcoming_job_count(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.upcoming_job_count = sum(
                1
                for j in rec.job_ids
                if j.start_datetime
                and j.start_datetime >= now
                and j.state not in ("completed", "cancelled")
            )

    def action_view_jobs(self):
        self.ensure_one()
        return {
            "name": f"{self.name} — Jobs",
            "type": "ir.actions.act_window",
            "res_model": "platform.planning.job",
            "view_mode": "list,kanban,form",
            "domain": [("resource_ids", "in", [self.id])],
        }
