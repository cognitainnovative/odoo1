"""Agent skill catalogue and per-user chat availability flag."""

from odoo import fields, models


class ChatAgentSkill(models.Model):
    _name = "chat.agent.skill"
    _description = "Chat Agent Skill"
    _order = "name"

    name = fields.Char(required=True)
    description = fields.Text()
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    active = fields.Boolean(default=True)

    _skill_name_uniq = models.Constraint(
        "UNIQUE(company_id, name)",
        "Skill name must be unique per company.",
    )


class ResUsersChat(models.Model):
    _inherit = "res.users"

    available_for_chat = fields.Boolean(
        "Available for Chat",
        default=False,
        help=(
            "When enabled, this agent appears in the escalation priority list and the "
            "session transfer dropdown. Toggle off when unavailable (lunch, EOD, etc.)."
        ),
    )
    chat_skill_ids = fields.Many2many(
        "chat.agent.skill",
        "res_users_chat_skill_rel",
        "user_id",
        "skill_id",
        "Chat Skills",
        help="Skills this agent handles — used to match escalated sessions.",
    )
