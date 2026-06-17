"""Central immutable audit log.

Covers: payroll access, financial records, signing events, AI outputs,
admin overrides, GDPR requests, API token events.

Design: create-only. write() and unlink() are hard-blocked for ALL users
including superuser, because immutability is the point.
"""

import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Event type taxonomy — extend by adding values here only
AUDIT_EVENT_TYPES = [
    # Finance
    ("financial_read", "Financial Record — Read"),
    ("financial_write", "Financial Record — Write"),
    ("financial_export", "Financial Record — Export"),
    # Payroll
    ("payroll_access", "Payroll — Record Accessed"),
    ("payroll_export", "Payroll — Export / Filing"),
    ("payroll_override", "Payroll — Admin Override"),
    # Signing
    ("signing_signed", "Quote / Document — Signed"),
    ("signing_rejected", "Quote / Document — Rejected"),
    ("signing_voided", "Quote / Document — Voided"),
    # AI
    ("ai_call", "AI — External Call Made"),
    ("ai_redacted", "AI — PII Redacted Before Call"),
    ("ai_error", "AI — Call Failed"),
    # Admin
    ("admin_override", "Admin — Security Override"),
    ("admin_config_change", "Admin — Configuration Changed"),
    # Auth / tokens
    ("token_issued", "API Token — Issued"),
    ("token_revoked", "API Token — Revoked"),
    ("token_used", "API Token — Used"),
    # GDPR
    ("gdpr_export", "GDPR — Data Export"),
    ("gdpr_anonymize", "GDPR — Anonymisation"),
    ("gdpr_delete", "GDPR — Deletion Request"),
    ("gdpr_consent_given", "GDPR — Consent Recorded"),
    ("gdpr_consent_revoked", "GDPR — Consent Revoked"),
    ("gdpr_portability", "GDPR — Data Portability"),
    ("gdpr_rectification", "GDPR — Data Rectification"),
    # Email
    ("email_sent", "Email — Sent"),
]


class PlatformAuditLog(models.Model):
    _name = "platform.audit.log"
    _description = "Platform Audit Log"
    _order = "create_date desc"
    _log_access = True

    company_id = fields.Many2one(
        "res.company",
        index=True,
        readonly=True,
        default=lambda s: s.env.company,
    )
    user_id = fields.Many2one(
        "res.users",
        "User",
        index=True,
        readonly=True,
        default=lambda s: s.env.user,
        ondelete="set null",
    )
    event_type = fields.Selection(AUDIT_EVENT_TYPES, required=True, readonly=True, index=True)
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("critical", "Critical")],
        default="info",
        readonly=True,
    )

    # Affected record
    res_model = fields.Char("Model", readonly=True, index=True)
    res_id = fields.Integer("Record ID", readonly=True, index=True)
    res_name = fields.Char("Record Name", readonly=True)

    # Request context
    ip_address = fields.Char("IP Address", readonly=True)
    session_id = fields.Char("Session ID", readonly=True)

    # Payload (JSON — keys are domain-specific, never store raw PII here)
    details = fields.Text("Details (JSON)", readonly=True)

    # Human-readable summary for the log list view
    summary = fields.Char("Summary", readonly=True)

    # ── Immutability ────────────────────────────────────────────────────────────

    def write(self, vals):
        raise UserError("Audit log records are immutable and cannot be modified.")

    def unlink(self):
        raise UserError("Audit log records cannot be deleted.")

    # ── Factory ─────────────────────────────────────────────────────────────────

    @api.model
    def log(
        self,
        event_type: str,
        *,
        res_model: str = "",
        res_id: int = 0,
        res_name: str = "",
        summary: str = "",
        details: dict | None = None,
        severity: str = "info",
        user=None,
        company=None,
    ) -> "PlatformAuditLog":
        """Create an immutable audit log entry. Call via sudo() from business code."""
        req = None
        ip = ""
        session = ""
        try:
            from odoo.http import request as http_req  # noqa: PLC0415

            if http_req:
                req = http_req
                ip = (
                    req.httprequest.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                    or req.httprequest.remote_addr
                    or ""
                )
                session = getattr(req.session, "sid", "")
        except Exception:
            pass

        return self.sudo().create(
            {
                "company_id": (company or self.env.company).id,
                "user_id": (user or self.env.user).id,
                "event_type": event_type,
                "severity": severity,
                "res_model": res_model,
                "res_id": res_id,
                "res_name": res_name[:255] if res_name else "",
                "summary": summary[:500] if summary else "",
                "details": json.dumps(details, default=str) if details else "",
                "ip_address": ip[:64] if ip else "",
                "session_id": session[:128] if session else "",
            }
        )
