"""Extend res.partner with GDPR consent fields for CRM."""

import hashlib

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    gdpr_consent = fields.Boolean("GDPR Consent", default=False)
    gdpr_consent_date = fields.Datetime("Consent Date")
    gdpr_consent_version = fields.Char("Privacy Policy Version")
    gdpr_anonymized = fields.Boolean("Anonymized", default=False, readonly=True)
    anonymize_date = fields.Datetime("Anonymized On", readonly=True)

    crm_lead_ids = fields.One2many("crm.lead", "partner_id", "Leads / Deals")
    crm_lead_count = fields.Integer(compute="_compute_crm_lead_count")

    @api.depends("crm_lead_ids")
    def _compute_crm_lead_count(self):
        for rec in self:
            rec.crm_lead_count = len(rec.crm_lead_ids)

    def action_anonymize_partner(self):
        """GDPR right-to-erasure: anonymize personal data on this contact."""
        for partner in self:
            if partner.gdpr_anonymized:
                continue
            anon_hash = hashlib.sha256(str(partner.id).encode()).hexdigest()[:8]
            partner.write(
                {
                    "name": f"[Anonymized-{anon_hash}]",
                    "email": f"anon-{anon_hash}@redacted.invalid",
                    "phone": False,
                    "street": False,
                    "street2": False,
                    "zip": False,
                    "city": False,
                    "website": False,
                    "vat": False,
                    "comment": "[Content removed — GDPR anonymization]",
                    "gdpr_anonymized": True,
                    "anonymize_date": fields.Datetime.now(),
                }
            )
            # Anonymize linked leads too
            partner.crm_lead_ids.action_anonymize()

    def action_export_gdpr_data(self):
        """Export personal data for GDPR subject access request."""
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "company": self.commercial_partner_id.name,
            "address": (
                f"{self.street or ''} {self.city or ''} {self.country_id.name or ''}".strip()
            ),
            "gdpr_consent": self.gdpr_consent,
            "gdpr_consent_date": str(self.gdpr_consent_date) if self.gdpr_consent_date else None,
            "leads": [
                {"id": lead.id, "name": lead.name, "stage": lead.stage_id.name}
                for lead in self.crm_lead_ids
            ],
        }

    def action_view_crm_leads(self):
        self.ensure_one()
        return {
            "name": f"{self.name} — Leads",
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "kanban,list,form",
            "domain": [("partner_id", "=", self.id)],
        }
