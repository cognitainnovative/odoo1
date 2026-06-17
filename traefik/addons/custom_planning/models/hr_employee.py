"""Extend hr.employee with planning availability and skills for job assignment."""

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    planning_job_ids = fields.One2many("platform.planning.job", "employee_id", "Assigned Jobs")
    planning_job_count = fields.Integer(compute="_compute_planning_job_count")
    planning_skills = fields.Char(
        "Planning Skills",
        help="Comma-separated skill tags for job matching (e.g. 'electrician, forklift, Dutch').",
    )
    planning_available = fields.Boolean(
        "Available for Planning",
        default=True,
        help="Uncheck to hide this employee from the job assignment dropdown.",
    )

    def _compute_planning_job_count(self):
        now = fields.Datetime.now()
        for emp in self:
            emp.planning_job_count = self.env["platform.planning.job"].search_count(
                [
                    ("employee_id", "=", emp.id),
                    ("start_datetime", ">=", now),
                    ("state", "not in", ("completed", "cancelled")),
                ]
            )

    def action_view_planning_jobs(self):
        self.ensure_one()
        return {
            "name": f"{self.name} — Planning Jobs",
            "type": "ir.actions.act_window",
            "res_model": "platform.planning.job",
            "view_mode": "list,kanban,form",
            "domain": [("employee_id", "=", self.id)],
        }
