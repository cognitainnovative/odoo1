"""Wizard that issues an API token and displays the raw value exactly once.

This is the only place the raw token ever exists in Python memory. The token
model itself stores only the SHA-256 hash; this transient wizard holds the raw
value just long enough for the admin to copy it, then vanishes with the
transient-record vacuum.
"""

from odoo import fields, models


class PlatformApiTokenGenerate(models.TransientModel):
    _name = "platform.api.token.generate"
    _description = "Generate API Token"

    name = fields.Char("Label", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    user_id = fields.Many2one(
        "res.users",
        "Acts As (User)",
        required=True,
        help="The Odoo user whose permissions apply when this token is used. "
        "Never use an admin user here unless absolutely required.",
    )
    service = fields.Selection(
        [
            ("react_app", "React Support App"),
            ("fastapi", "FastAPI Service"),
            ("webhook", "Incoming Webhook"),
            ("ci", "CI / Test Runner"),
            ("other", "Other"),
        ],
        required=True,
        default="other",
    )
    scope = fields.Selection(
        [
            ("read", "Read-only"),
            ("write", "Read + Write"),
            ("admin", "Admin (full access for this user)"),
        ],
        required=True,
        default="read",
    )
    expires_at = fields.Datetime(
        "Expires At",
        help="Leave empty for a non-expiring token (not recommended for production).",
    )
    notes = fields.Text()

    # Filled after generation; shown once in the same dialog.
    raw_token = fields.Char("Token (copy now — shown only once)", readonly=True)
    token_id = fields.Many2one("platform.api.token", readonly=True)

    def action_generate(self):
        self.ensure_one()
        Token = self.env["platform.api.token"]
        raw = Token._new_raw_token()
        token = Token.create(
            {
                "name": self.name,
                "company_id": self.company_id.id,
                "user_id": self.user_id.id,
                "service": self.service,
                "scope": self.scope,
                "expires_at": self.expires_at,
                "notes": self.notes,
                "token_hash": Token._hash_token(raw),
            }
        )
        self.write({"raw_token": raw, "token_id": token.id})
        # Reopen the same wizard so the raw token is displayed once.
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
