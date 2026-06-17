"""Extend crm.lead with AI scoring, GDPR consent, campaign, duplicate detection."""

import hashlib
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # ── AI scoring & summary ──────────────────────────────────────────────────
    lead_score = fields.Integer(
        "Lead Score",
        compute="_compute_lead_score",
        store=True,
        help="Rule-based score 0-100. Higher = hotter lead.",
    )
    ai_summary = fields.Text("AI Summary", readonly=True)
    ai_summary_date = fields.Datetime("Summary Generated", readonly=True)

    # ── Campaign & source ─────────────────────────────────────────────────────
    platform_campaign_id = fields.Many2one(
        "crm.campaign",
        "Platform Campaign",
        domain="[('company_id', '=', company_id)]",
        index=True,
    )
    lead_source_detail = fields.Char("Source Detail", help="e.g. 'Google Ads – Brand campaign'")

    # ── GDPR ──────────────────────────────────────────────────────────────────
    gdpr_consent = fields.Boolean("GDPR Consent Given", default=False)
    gdpr_consent_date = fields.Datetime("Consent Date")
    gdpr_consent_ip = fields.Char("Consent IP")
    gdpr_consent_version = fields.Char("Privacy Policy Version")
    gdpr_anonymized = fields.Boolean("Anonymized", default=False, readonly=True)

    # ── Duplicate detection ───────────────────────────────────────────────────
    duplicate_lead_ids = fields.Many2many(
        "crm.lead",
        "crm_lead_duplicate_rel",
        "lead_id",
        "duplicate_id",
        "Duplicate Leads",
        compute="_compute_duplicates",
        compute_sudo=False,
        store=False,
    )
    duplicate_count = fields.Integer(compute="_compute_duplicates", compute_sudo=False)

    # ── Follow-up ─────────────────────────────────────────────────────────────
    next_follow_up_date = fields.Date("Next Follow-up")
    follow_up_notes = fields.Text("Follow-up Notes")

    # ── Extra tracking ────────────────────────────────────────────────────────
    last_contacted_date = fields.Datetime("Last Contacted", readonly=True)
    contact_count = fields.Integer("Contact Attempts", default=0, readonly=True)

    # ── Custom fields (company-defined EAV values) ────────────────────────────
    custom_field_value_ids = fields.One2many("crm.custom.field.value", "lead_id", "Custom Fields")

    # ── Score computation ─────────────────────────────────────────────────────

    @api.depends(
        "email_from",
        "phone",
        "partner_id",
        "partner_id.website",
        "probability",
        "expected_revenue",
        "partner_name",
        "platform_campaign_id",
    )
    def _compute_lead_score(self):
        for lead in self:
            score = 0
            if lead.email_from:
                score += 20
            if lead.phone:
                score += 15
            if lead.partner_id and lead.partner_id.website:
                score += 5
            if lead.partner_id:
                score += 10
            if lead.expected_revenue and lead.expected_revenue > 0:
                score += min(int(lead.expected_revenue / 1000) * 2, 20)
            if lead.probability and lead.probability > 50:
                score += 15
            if lead.platform_campaign_id:
                score += 5
            lead.lead_score = min(score, 100)

    # ── Duplicate detection ───────────────────────────────────────────────────

    @api.depends("email_from", "partner_name")
    def _compute_duplicates(self):
        for lead in self:
            dupes = self.env["crm.lead"].browse()
            # Explicit company scope (defense-in-depth on top of record rules)
            # so duplicate detection can never surface another company's leads.
            company_domain = [("company_id", "=", lead.company_id.id)] if lead.company_id else []
            if lead.email_from:
                dupes |= self.search(
                    [
                        ("id", "!=", lead.id or 0),
                        ("email_from", "=ilike", lead.email_from),
                        ("active", "in", [True, False]),
                    ]
                    + company_domain,
                    limit=10,
                )
            if lead.partner_name and len(lead.partner_name) > 3:
                dupes |= self.search(
                    [
                        ("id", "!=", lead.id or 0),
                        ("partner_name", "ilike", lead.partner_name),
                        ("active", "in", [True, False]),
                    ]
                    + company_domain,
                    limit=5,
                )
            lead.duplicate_lead_ids = dupes
            lead.duplicate_count = len(dupes)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_generate_ai_summary(self):
        """Call AI service to generate a lead summary.

        Passes lead data as template_vars so the versioned crm_lead_summary
        template ({name}/{company}/{stage}/{notes}) is rendered with real
        values. A fallback user_prompt is supplied in case the template is
        missing.
        """
        for lead in self:
            company_name = ""
            if lead.partner_id:
                company_name = lead.partner_id.commercial_partner_id.name or ""
            company_name = company_name or lead.partner_name or ""
            tmpl_vars = {
                "name": lead.name or "",
                "company": company_name,
                "stage": lead.stage_id.name or "Unknown",
                "notes": lead.description or "",
            }
            result = self.env["ai.service"].call(
                user_prompt=(
                    f"Summarise this sales lead in 3 sentences for a sales manager:\n"
                    f"Name: {lead.name}\n"
                    f"Company: {company_name or 'Unknown'}\n"
                    f"Stage: {lead.stage_id.name or 'Unknown'}\n"
                    f"Score: {lead.lead_score}/100\n"
                    f"Notes: {lead.description or ''}"
                ),
                template_code="crm_lead_summary",
                template_vars=tmpl_vars,
                res_model=self._name,
                res_id=lead.id,
            )
            if result["ok"]:
                lead.write(
                    {
                        "ai_summary": result["content"],
                        "ai_summary_date": fields.Datetime.now(),
                    }
                )
            else:
                _logger.warning("AI summary failed for lead %d: %s", lead.id, result["error"])
        return True

    def action_ai_followup_suggestion(self):
        """Ask AI for a follow-up suggestion for this lead."""
        self.ensure_one()
        result = self.env["ai.service"].call(
            user_prompt=(
                f"Suggest the best next action for this lead:\n"
                f"Lead: {self.name}\nStage: {self.stage_id.name}\n"
                f"Score: {self.lead_score}/100\n"
                f"Notes: {self.description or ''}"
            ),
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "AI Follow-up Suggestion",
                    "message": result["content"][:300],
                    "type": "info",
                    "sticky": True,
                },
            }
        raise UserError(f"AI suggestion failed: {result['error']}")

    def action_view_duplicates(self):
        self.ensure_one()
        return {
            "name": f"Duplicates of: {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "list,form",
            "domain": [("id", "in", self.duplicate_lead_ids.ids)],
        }

    def action_mark_contacted(self):
        """Record a contact attempt."""
        self.write(
            {
                "last_contacted_date": fields.Datetime.now(),
                "contact_count": self.contact_count + 1,
            }
        )

    def action_record_gdpr_consent(self):
        """Record explicit GDPR consent."""
        self.write(
            {
                "gdpr_consent": True,
                "gdpr_consent_date": fields.Datetime.now(),
            }
        )
        if self.partner_id:
            self.partner_id.write(
                {"gdpr_consent": True, "gdpr_consent_date": fields.Datetime.now()}
            )

    def action_export_csv(self):
        """Return a URL action that downloads leads as CSV via the controller."""
        return {
            "type": "ir.actions.act_url",
            "url": "/api/leads/export.csv",
            "target": "self",
        }

    @api.model
    def _cron_send_followup_reminders(self):
        """Cron: create activity reminders for leads with overdue follow-up dates."""
        today = fields.Date.today()
        overdue = self.search(
            [
                ("next_follow_up_date", "<=", today),
                ("probability", "<", 100),
                ("active", "=", True),
            ]
        )
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for lead in overdue:
            # Skip if an open reminder activity already exists
            existing = self.env["mail.activity"].search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", lead.id),
                    ("activity_type_id", "=", activity_type.id if activity_type else False),
                ],
                limit=1,
            )
            if existing:
                continue
            lead.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=today,
                summary=f"Follow-up overdue: {lead.name}",
                user_id=lead.user_id.id or self.env.uid,
            )
        _logger.info("Follow-up reminders created for %d leads.", len(overdue))

    def action_anonymize(self):
        """Anonymize this lead's personal data for GDPR compliance."""
        for lead in self:
            if lead.gdpr_anonymized:
                continue
            anon_hash = hashlib.sha256(str(lead.id).encode()).hexdigest()[:8]
            lead.write(
                {
                    "partner_name": f"[Anonymized-{anon_hash}]",
                    "contact_name": f"[Anonymized-{anon_hash}]",
                    "email_from": f"anon-{anon_hash}@redacted.invalid",
                    "phone": False,
                    "partner_id": False,
                    "description": "[Content removed — GDPR anonymization]",
                    "gdpr_anonymized": True,
                }
            )

    def action_export_gdpr_data(self):
        """Return a dict of personal data for GDPR export."""
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "partner_name": self.partner_name,
            "contact_name": self.contact_name,
            "email": self.email_from,
            "phone": self.phone,
            "stage": self.stage_id.name,
            "probability": self.probability,
            "expected_revenue": self.expected_revenue,
            "gdpr_consent": self.gdpr_consent,
            "gdpr_consent_date": str(self.gdpr_consent_date) if self.gdpr_consent_date else None,
            "campaign": self.platform_campaign_id.name if self.platform_campaign_id else None,
            "created": str(self.create_date),
        }
