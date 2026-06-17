"""Extend res.company with data-residency, GDPR DPO contact, and retention settings."""

from odoo import fields, models


class ResCompanySecurityExt(models.Model):
    _inherit = "res.company"

    # ── Data residency ──────────────────────────────────────────────────────────

    ai_data_residency = fields.Selection(
        [
            ("local_eu", "Local / EU only (default — Ollama or EU-hosted provider)"),
            ("external_opt_in", "External AI allowed (explicit company opt-in)"),
        ],
        "AI Data Residency",
        default="local_eu",
        help=(
            "Controls where AI processing may occur.\n"
            "• local_eu: embeddings and inference stay on-premises or within EU. "
            "Payroll and financial data NEVER leave this boundary regardless of setting.\n"
            "• external_opt_in: company has explicitly opted to allow non-EU providers "
            "(e.g. OpenAI, Anthropic) for non-sensitive content."
        ),
    )

    # ── GDPR DPO ────────────────────────────────────────────────────────────────

    gdpr_dpo_name = fields.Char("Data Protection Officer (DPO)")
    gdpr_dpo_email = fields.Char("DPO Email")
    gdpr_dpo_phone = fields.Char("DPO Phone")
    gdpr_privacy_url = fields.Char(
        "Privacy Policy URL",
        help="Shown to visitors in the chat widget consent banner.",
    )

    # ── Default retention ───────────────────────────────────────────────────────

    gdpr_default_retention_days = fields.Integer(
        "Default Data Retention (days)",
        default=730,
        help=(
            "Used when no per-model policy is configured. "
            "Minimum recommended: 365 days for operational data, "
            "7 years (2555 days) for financial records (Dutch law)."
        ),
    )
    gdpr_financial_retention_days = fields.Integer(
        "Financial Record Retention (days)",
        default=2555,
        help="Dutch law requires 7 years (2555 days) for financial records.",
    )
    gdpr_payroll_retention_days = fields.Integer(
        "Payroll Record Retention (days)",
        default=2555,
        help="Dutch law requires 7 years for payroll / tax records.",
    )
    gdpr_audit_log_retention_days = fields.Integer(
        "Audit Log Retention (days)",
        default=2555,
        help="Audit logs should be kept for at least 7 years per Dutch law.",
    )
