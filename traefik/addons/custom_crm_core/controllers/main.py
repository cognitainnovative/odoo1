"""Lead capture API and CSV export endpoints."""

import csv
import io
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CrmLeadCaptureController(http.Controller):

    @http.route(
        "/api/leads",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def capture_lead(self, **kwargs):
        """Public JSON endpoint for web-form / external lead capture.

        Expected body keys (all optional except ``name`` or ``email``):
            name, email, phone, company, contact_name, message, source,
            gdpr_consent (bool), campaign_id (int).
        """
        vals = {
            "name": kwargs.get("name") or "Web Lead",
            "type": "lead",
            "email_from": kwargs.get("email"),
            "phone": kwargs.get("phone"),
            "partner_name": kwargs.get("company"),
            "contact_name": kwargs.get("contact_name"),
            "description": kwargs.get("message"),
            "lead_source_detail": kwargs.get("source"),
        }
        if kwargs.get("campaign_id"):
            vals["platform_campaign_id"] = int(kwargs["campaign_id"])
        if kwargs.get("gdpr_consent"):
            vals["gdpr_consent"] = True
            vals["gdpr_consent_date"] = fields.Datetime.now()
            vals["gdpr_consent_ip"] = request.httprequest.remote_addr
        try:
            lead = request.env["crm.lead"].sudo().create(vals)
            _logger.info("Lead captured via API: id=%d email=%s", lead.id, vals.get("email_from"))
            return {"ok": True, "id": lead.id, "name": lead.name}
        except Exception as exc:
            _logger.error("Lead capture failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    @http.route(
        "/api/leads/export.csv",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def export_leads_csv(self, **kwargs):
        """Download all leads as CSV. Requires a logged-in user."""
        columns = [
            "name",
            "partner_name",
            "email_from",
            "phone",
            "stage_id",
            "probability",
            "expected_revenue",
            "lead_score",
            "gdpr_consent",
            "create_date",
        ]
        leads = request.env["crm.lead"].search_read(
            domain=[("type", "=", "lead")],
            fields=columns,
            limit=10000,
        )
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            lead["stage_id"] = lead["stage_id"][1] if lead["stage_id"] else ""
            writer.writerow(lead)
        csv_bytes = output.getvalue().encode("utf-8")
        return request.make_response(
            csv_bytes,
            headers=[
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", 'attachment; filename="leads_export.csv"'),
                ("Content-Length", str(len(csv_bytes))),
            ],
        )
