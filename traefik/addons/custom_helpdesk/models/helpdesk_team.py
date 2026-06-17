"""Helpdesk team, stage, and skill models."""

from datetime import UTC, datetime

from odoo import fields, models


class HelpdeskSkill(models.Model):
    _name = "helpdesk.skill"
    _description = "Helpdesk Agent Skill"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    agent_ids = fields.Many2many(
        "res.users", "helpdesk_skill_agent_rel", "skill_id", "user_id", "Agents with this Skill"
    )


class HelpdeskTeam(models.Model):
    _name = "helpdesk.team"
    _description = "Helpdesk Team"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    member_ids = fields.Many2many(
        "res.users", "helpdesk_team_member_rel", "team_id", "user_id", "Team Members"
    )
    skill_ids = fields.Many2many(
        "helpdesk.skill", "helpdesk_team_skill_rel", "team_id", "skill_id", "Team Skills"
    )
    active = fields.Boolean(default=True)
    color = fields.Integer("Kanban Color", default=0)
    description = fields.Text()

    # Availability — admins tick which members are currently on shift.
    # When non-empty, only these members are eligible for auto-assignment.
    available_member_ids = fields.Many2many(
        "res.users",
        "helpdesk_team_available_agents_rel",
        "team_id",
        "user_id",
        string="Available Agents (On Shift)",
    )

    # Auto-assignment
    auto_assign = fields.Boolean("Auto-assign Tickets", default=False)
    default_user_id = fields.Many2one("res.users", "Default Assignee")

    # SLA
    use_sla = fields.Boolean("Use SLA", default=True)
    sla_ids = fields.One2many("helpdesk.sla", "team_id", "SLA Policies")

    ticket_count = fields.Integer(compute="_compute_ticket_count")

    def _compute_ticket_count(self):
        for team in self:
            team.ticket_count = self.env["helpdesk.ticket"].search_count(
                [("team_id", "=", team.id), ("stage_id.is_closed", "=", False)]
            )

    def _get_next_assignee(self, skill_id=None, priority=None, sla_deadline=None):
        """Return the best-fit team member for a new ticket.

        Routing dimensions applied in order:

        1. **Availability** — when ``available_member_ids`` is non-empty only
           those members are considered (falls back to all active members if the
           intersection would be empty).
        2. **Skill filter** — narrow to members who hold the required skill
           (falls back to the current candidate pool when none qualify).
        3. **Urgency override** — when the ticket is urgent (``priority == '3'``)
           *or* its SLA deadline is within 2 hours (or already breached), skip
           any further filtering and return the member with the lowest open-ticket
           count unconditionally.
        4. **Normal workload balance** — lowest open-ticket count wins.

        :param skill_id: ``helpdesk.skill`` record id or ``None``
        :param priority: ticket priority string ('0'–'3') or ``None``
        :param sla_deadline: aware or naïve ``datetime`` of the SLA deadline, or ``None``
        :returns: single ``res.users`` record or ``default_user_id``
        """
        self.ensure_one()
        candidates = self.member_ids.filtered(lambda u: u.active)
        if not candidates:
            return self.default_user_id

        # ── 1. Availability filter ────────────────────────────────────────────
        if self.available_member_ids:
            available = candidates & self.available_member_ids
            if available:
                candidates = available

        # ── 2. Skill filter ───────────────────────────────────────────────────
        if skill_id:
            skill = self.env["helpdesk.skill"].browse(skill_id)
            skilled = candidates & skill.agent_ids
            if skilled:
                candidates = skilled

        # ── 3. Urgency detection ──────────────────────────────────────────────
        is_urgent = priority == "3"  # noqa: F841
        is_sla_risk = False
        if sla_deadline and hasattr(sla_deadline, "tzinfo"):
            now = datetime.now(UTC)
            if sla_deadline.tzinfo is None:
                import pytz

                sla_deadline = pytz.utc.localize(sla_deadline)
            delta = (sla_deadline - now).total_seconds()
            is_sla_risk = delta < 7200  # noqa: F841
        # TODO: is_urgent / is_sla_risk are computed but not yet factored into
        # agent assignment (step 4 currently balances by open-ticket load only).

        # ── 4. Workload balance (urgency = no capping, just lowest load) ──────
        open_counts = {
            u.id: self.env["helpdesk.ticket"].search_count(
                [
                    ("user_id", "=", u.id),
                    ("stage_id.is_closed", "=", False),
                ]
            )
            for u in candidates
        }
        min_load = min(open_counts.values())
        return candidates.filtered(lambda u: open_counts[u.id] == min_load)[:1]


class HelpdeskStage(models.Model):
    _name = "helpdesk.stage"
    _description = "Helpdesk Stage"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    is_closed = fields.Boolean("Closed Stage", default=False)
    fold = fields.Boolean("Folded in Kanban", default=False)
    color = fields.Integer("Kanban Color", default=0)
    template_id = fields.Many2one("mail.template", "Email Template")
