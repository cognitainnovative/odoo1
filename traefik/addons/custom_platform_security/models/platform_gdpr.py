"""GDPR data management: export requests, anonymisation, retention policies.

Key GDPR rights implemented:
  - Art. 15 (access / export): platform.gdpr.request with type=export
  - Art. 17 (right to erasure / anonymise): type=anonymize or type=delete
  - Art. 5(1)(e) (storage limitation): platform.gdpr.retention.policy
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PlatformGdprRequest(models.Model):
    """Tracks data-subject requests (export, anonymise, delete)."""

    _name = "platform.gdpr.request"
    _description = "GDPR Data Subject Request"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)
    partner_id = fields.Many2one("res.partner", "Data Subject", required=True, ondelete="restrict")
    email = fields.Char(related="partner_id.email", readonly=True, store=True)
    request_type = fields.Selection(
        [
            ("export", "Data Export (Art. 15)"),
            ("anonymize", "Anonymise Data (Art. 17)"),
            ("delete", "Delete Data (Art. 17)"),
            ("portability", "Data Portability (Art. 20)"),
            ("rectification", "Data Rectification (Art. 16)"),
        ],
        required=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        tracking=True,
    )
    requested_date = fields.Date(default=fields.Date.today, readonly=True)
    deadline = fields.Date(
        "Legal Deadline",
        help="GDPR Art. 12: respond within 30 days of receipt.",
    )
    completed_date = fields.Date(readonly=True)
    processed_by_id = fields.Many2one("res.users", "Processed By", readonly=True)
    notes = fields.Text("Internal Notes")
    rejection_reason = fields.Text()

    # Export result
    export_attachment_id = fields.Many2one(
        "ir.attachment", "Export File", ondelete="set null", readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        import datetime  # noqa: PLC0415

        for vals in vals_list:
            if "deadline" not in vals:
                vals["deadline"] = (fields.Date.today() + datetime.timedelta(days=30)).isoformat()
        records = super().create(vals_list)
        event_map = {
            "export": "gdpr_export",
            "anonymize": "gdpr_anonymize",
            "delete": "gdpr_delete",
            "portability": "gdpr_portability",
            "rectification": "gdpr_rectification",
        }
        for rec in records:
            self.env["platform.audit.log"].log(
                event_map.get(rec.request_type, "gdpr_export"),
                res_model=self._name,
                res_id=rec.id,
                res_name=f"{rec.request_type} — {rec.partner_id.name}",
                summary=f"GDPR {rec.request_type} request for {rec.partner_id.name}",
                details={"request_type": rec.request_type, "partner_id": rec.partner_id.id},
                severity="warning",
            )
        return records

    def action_start(self):
        self.write({"state": "in_progress"})

    def action_complete(self):
        self.write(
            {
                "state": "completed",
                "completed_date": fields.Date.today(),
                "processed_by_id": self.env.user.id,
            }
        )

    def action_reject(self):
        self.write({"state": "rejected", "processed_by_id": self.env.user.id})

    def action_export_data(self):
        """Generate a JSON data export for the data subject and attach it."""
        self.ensure_one()
        if self.request_type != "export":
            raise UserError("This request is not a data export request.")
        import json  # noqa: PLC0415

        partner = self.partner_id
        payload = {
            "data_subject": {
                "name": partner.name,
                "email": partner.email,
                "phone": partner.phone,
            },
        }
        content = json.dumps(payload, indent=2, default=str).encode()
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"gdpr_export_{partner.id}.json",
                "type": "binary",
                "datas": __import__("base64").b64encode(content).decode(),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        self.export_attachment_id = attachment
        self.action_complete()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ir.attachment",
            "res_id": attachment.id,
            "view_mode": "form",
        }


class PlatformGdprRetentionPolicy(models.Model):
    """Per-model data retention policy — drives scheduled purge jobs."""

    _name = "platform.gdpr.retention.policy"
    _description = "GDPR Data Retention Policy"
    _order = "model_name"

    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    model_name = fields.Char(
        "Odoo Model",
        required=True,
        help="Technical model name (e.g. chat.transcript.line)",
    )
    retention_days = fields.Integer(
        "Retention (days)",
        required=True,
        default=365,
        help="Records older than this are eligible for purge.",
    )
    date_field = fields.Char(
        "Date Field",
        default="create_date",
        help="Field used to determine record age (must be a Date/Datetime field).",
    )
    last_purge_date = fields.Date("Last Purge Run", readonly=True)
    purge_count_last = fields.Integer("Records Purged (last run)", readonly=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    # Models the purge cron must NEVER hard-delete from, regardless of any
    # configured policy: legally-retained records (NL: 7y financial/payroll),
    # core master data, and the audit log (immutable by design — its own
    # unlink() raises, but blocklisting avoids noisy nightly exceptions).
    PURGE_PROTECTED_MODELS = frozenset(
        {
            "res.partner",
            "res.users",
            "res.company",
            "account.move",
            "account.move.line",
            "account.payment",
            "hr.employee",
            "hr.payslip",
            "hr.payslip.line",
            "platform.audit.log",
            "ir.attachment",
            "platform.gdpr.request",
            "platform.gdpr.retention.policy",
        }
    )

    PURGE_BATCH_SIZE = 1000  # unlink in batches to bound memory/locks
    PURGE_MAX_PER_RUN = 20000  # hard cap per model per nightly run

    @api.model
    def cron_purge_expired_records(self):
        """Called daily by ir.cron — deletes records past their retention.

        Safeguards: protected-model blocklist, batched unlink, per-run cap.
        A misconfigured policy on a protected model is skipped and logged
        rather than executed.
        """
        today = fields.Date.today()
        import datetime  # noqa: PLC0415

        for policy in self.search([("active", "=", True)]):
            if policy.retention_days <= 0:
                continue
            if policy.model_name in self.PURGE_PROTECTED_MODELS:
                _logger.warning(
                    "GDPRRetention: policy %s targets protected model %s — SKIPPED. "
                    "Protected models must be anonymised via a GDPR request, "
                    "never bulk-purged.",
                    policy.id,
                    policy.model_name,
                )
                continue
            cutoff = today - datetime.timedelta(days=policy.retention_days)
            try:
                model = self.env.get(policy.model_name)
                if model is None:
                    _logger.warning(
                        "GDPRRetention: model %s not found, skipping", policy.model_name
                    )
                    continue
                date_field = policy.date_field or "create_date"
                if date_field not in model._fields:
                    _logger.warning(
                        "GDPRRetention: field %s not on %s, skipping",
                        date_field,
                        policy.model_name,
                    )
                    continue
                domain = [(date_field, "<", cutoff.isoformat())]
                total = 0
                while total < self.PURGE_MAX_PER_RUN:
                    batch = model.sudo().search(domain, limit=self.PURGE_BATCH_SIZE)
                    if not batch:
                        break
                    count = len(batch)
                    batch.unlink()
                    total += count
                    self.env.cr.commit()  # release locks between batches
                if total:
                    _logger.info(
                        "GDPRRetention: purged %d records from %s (cutoff %s)",
                        total,
                        policy.model_name,
                        cutoff,
                    )
                policy.sudo().write(
                    {
                        "last_purge_date": today,
                        "purge_count_last": total,
                    }
                )
            except Exception:
                _logger.exception("GDPRRetention: error purging %s", policy.model_name)
