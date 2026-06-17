"""Prompt template store with versioning."""

from odoo import api, fields, models


class AiPromptTemplate(models.Model):
    _name = "ai.prompt.template"
    _description = "AI Prompt Template"
    _order = "category, name, version desc"
    _rec_name = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True, help="Stable identifier used in code calls.")
    category = fields.Selection(
        [
            ("crm", "CRM"),
            ("helpdesk", "Helpdesk"),
            ("email", "Email"),
            ("accounting", "Accounting"),
            ("hr", "HR / Payroll"),
            ("general", "General"),
        ],
        default="general",
    )
    version = fields.Integer(default=1, readonly=True)
    is_active = fields.Boolean("Active Version", default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )

    # Prompt content
    system_prompt = fields.Text("System Prompt")
    user_template = fields.Text(
        "User Prompt Template",
        help="Use {variable} placeholders. These are filled via render().",
    )
    output_format = fields.Selection(
        [("text", "Plain Text"), ("json", "JSON"), ("markdown", "Markdown")],
        default="text",
    )
    max_tokens = fields.Integer("Max Tokens Override", default=0, help="0 = use provider default.")
    temperature_override = fields.Float(
        "Temperature Override", default=-1.0, digits=(4, 2), help="-1 = use provider default."
    )

    notes = fields.Text()
    previous_version_id = fields.Many2one("ai.prompt.template", "Previous Version", readonly=True)

    _code_company_version_uniq = models.Constraint(
        "UNIQUE(code, company_id, version)",
        "Template code + version must be unique per company.",
    )

    def render(self, variables: dict | None = None) -> tuple[str | None, str]:
        """Return (system_prompt, user_prompt) with variables substituted.

        Missing placeholders are filled with an empty string rather than
        leaving literal "{placeholder}" text in the prompt (which would be sent
        verbatim to the model). Uses a defaulting dict so unknown keys don't
        raise and don't leak braces.
        """
        self.ensure_one()
        variables = variables or {}
        system = self.system_prompt or None

        class _Default(dict):
            def __missing__(self, key):
                return ""

        try:
            user = (self.user_template or "").format_map(_Default(variables))
        except (ValueError, IndexError):
            # Malformed template (e.g. stray brace) — fall back to raw text.
            user = self.user_template or ""
        return system, user

    def action_new_version(self):
        """Create a new draft version of this template."""
        self.ensure_one()
        new = self.copy(
            {
                "version": self.version + 1,
                "is_active": False,
                "previous_version_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "ai.prompt.template",
            "res_id": new.id,
            "view_mode": "form",
        }

    @api.model
    def get_template(self, code: str, company_id: int | None = None) -> "AiPromptTemplate | None":
        """Fetch the active version of a template by code for the current company."""
        cid = company_id or self.env.company.id
        rec = self.search(
            [("code", "=", code), ("company_id", "=", cid), ("is_active", "=", True)],
            order="version desc",
            limit=1,
        )
        return rec or None
