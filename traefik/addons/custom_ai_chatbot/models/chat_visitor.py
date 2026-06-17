"""Website visitor tracking — consent-aware, minimal PII."""

import logging
import secrets

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatVisitor(models.Model):
    _name = "chat.visitor"
    _description = "Website Visitor"
    _order = "last_seen desc"

    # Token for session continuity (no PII)
    token = fields.Char(index=True, copy=False, readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)

    # Consent tracking
    tracking_consent = fields.Boolean(
        "Tracking Consent Given",
        default=False,
        help="We only track page visits after explicit consent.",
    )
    consent_date = fields.Datetime(readonly=True)
    consent_revoked_date = fields.Datetime(
        "Consent Revoked",
        readonly=True,
        help="Set when the visitor explicitly withdraws tracking consent (GDPR right to withdraw).",
    )

    # Identity (only known after form submission or login)
    partner_id = fields.Many2one("res.partner", "Identified Contact", ondelete="set null")
    email = fields.Char(
        "Email", help="Only populated after visitor submits a form or identifies themselves."
    )
    company_name = fields.Char("Visitor Company")

    # Session data
    first_seen = fields.Datetime(readonly=True)
    last_seen = fields.Datetime(readonly=True)
    page_view_count = fields.Integer(readonly=True, default=0)
    referrer = fields.Char(readonly=True)
    utm_source = fields.Char(readonly=True)
    utm_medium = fields.Char(readonly=True)
    utm_campaign = fields.Char(readonly=True)
    country_id = fields.Many2one("res.country", readonly=True)
    language_code = fields.Char(readonly=True)

    # Linked records
    lead_id = fields.Many2one("crm.lead", "Linked Lead", ondelete="set null")
    chat_session_ids = fields.One2many("chat.session", "visitor_id", "Chat Sessions")
    chat_session_count = fields.Integer(compute="_compute_chat_count")

    @api.depends("chat_session_ids")
    def _compute_chat_count(self):
        for vis in self:
            vis.chat_session_count = len(vis.chat_session_ids)

    @api.model
    def get_or_create_visitor(self, token: str | None = None) -> "ChatVisitor":
        """Get visitor by token or create a new one."""
        if token:
            visitor = self.search([("token", "=", token)], limit=1)
            if visitor:
                visitor.last_seen = fields.Datetime.now()
                return visitor
        new_token = secrets.token_urlsafe(32)
        return self.create(
            {
                "token": new_token,
                "first_seen": fields.Datetime.now(),
                "last_seen": fields.Datetime.now(),
            }
        )

    def record_consent(self):
        self.write(
            {
                "tracking_consent": True,
                "consent_date": fields.Datetime.now(),
                "consent_revoked_date": False,
            }
        )

    def revoke_consent(self):
        """Withdraw tracking consent — immediately stops page-view recording (GDPR Art. 7(3))."""
        self.write(
            {
                "tracking_consent": False,
                "consent_revoked_date": fields.Datetime.now(),
            }
        )

    def record_page_view(self, url: str = "", referrer: str = ""):
        if self.tracking_consent and not self.consent_revoked_date:
            self.page_view_count += 1
            if referrer and not self.referrer:
                self.referrer = referrer[:500]
