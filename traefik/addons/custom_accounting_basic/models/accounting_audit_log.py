"""Immutable audit log for accounting events (invoice posting, AI matching, imports, etc.)."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountingAuditLog(models.Model):
    _name = "accounting.audit.log"
    _description = "Accounting Audit Log"
    _order = "timestamp desc, id desc"
    _rec_name = "event_type"

    event_type = fields.Selection(
        [
            ("invoice_posted", "Invoice Posted"),
            ("invoice_cancelled", "Invoice Cancelled"),
            ("credit_note_created", "Credit Note Created"),
            ("payment_matched", "Payment Matched"),
            ("payment_reminder_sent", "Payment Reminder Sent"),
            ("bank_import", "Bank Statement Imported"),
            ("ai_match_accepted", "AI Match Accepted"),
            ("ai_extraction", "AI Invoice Extracted"),
            ("recurring_created", "Recurring Invoice Created"),
            ("manual_reconcile", "Manual Reconciliation"),
            ("approval", "Invoice Approved for Booking"),
        ],
        string="Event",
        required=True,
        index=True,
    )
    res_model = fields.Char("Document Model", index=True)
    res_id = fields.Integer("Document ID", index=True)
    document_ref = fields.Char("Document Reference")
    user_id = fields.Many2one(
        "res.users",
        "User",
        default=lambda self: self.env.user,
        readonly=True,
        ondelete="set null",
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        default=lambda self: self.env.company,
        readonly=True,
    )
    timestamp = fields.Datetime("Timestamp", default=fields.Datetime.now, readonly=True, index=True)
    details = fields.Text("Details", readonly=True)

    def write(self, vals):
        raise UserError("Accounting audit log entries are immutable and cannot be modified.")

    def unlink(self):
        raise UserError("Accounting audit log entries cannot be deleted.")

    # Events that warrant a central platform audit log entry
    _PLATFORM_LOG_EVENTS = frozenset(
        {
            "invoice_posted",
            "invoice_cancelled",
            "credit_note_created",
            "approval",
            "ai_extraction",
            "ai_match_accepted",
        }
    )

    @api.model
    def log(
        self,
        event_type: str,
        res_model: str = None,
        res_id: int = None,
        document_ref: str = None,
        details: str = None,
    ) -> "AccountingAuditLog":
        """Convenience method: create a single audit log entry."""
        record = self.create(
            {
                "event_type": event_type,
                "res_model": res_model,
                "res_id": res_id,
                "document_ref": document_ref,
                "details": details,
            }
        )
        if event_type in self._PLATFORM_LOG_EVENTS:
            try:
                self.env["platform.audit.log"].sudo().log(
                    "financial_write",
                    res_model=res_model or self._name,
                    res_id=res_id,
                    res_name=document_ref,
                    summary=f"Financial event '{event_type}' on {document_ref or res_model}",
                    details={"event_type": event_type, "details": details},
                    severity="warning",
                )
            except Exception:
                _logger.exception("Failed to emit financial event to platform.audit.log")
        return record
