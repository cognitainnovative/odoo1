"""Extend res.company with AI settings."""

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Backward-compat alias: True when ai_data_residency == 'external_opt_in'
    # The authoritative field is ai_data_residency in custom_platform_security.
    ai_allow_external = fields.Boolean(
        "Allow External AI Calls",
        compute="_compute_ai_allow_external",
        inverse="_inverse_ai_allow_external",
        store=False,
        help=(
            "Derived from AI Data Residency setting. "
            "Payroll and financial data is NEVER sent externally regardless of this setting."
        ),
    )

    @api.depends("ai_data_residency")
    def _compute_ai_allow_external(self):
        for rec in self:
            rec.ai_allow_external = rec.ai_data_residency == "external_opt_in"

    def _inverse_ai_allow_external(self):
        for rec in self:
            rec.ai_data_residency = "external_opt_in" if rec.ai_allow_external else "local_eu"

    ai_privacy_redaction = fields.Boolean(
        "Enable PII Redaction",
        default=True,
        help="Redact emails, phone numbers, BSN, IBAN, etc. before sending to external AI.",
    )
    ai_default_provider_id = fields.Many2one(
        "ai.provider",
        "Default AI Provider",
        domain="[('company_id', '=', id), ('is_active', '=', True)]",
    )
