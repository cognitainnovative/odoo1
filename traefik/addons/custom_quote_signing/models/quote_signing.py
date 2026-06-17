"""Immutable signing audit record — every signing event is captured here."""

import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class QuoteSigning(models.Model):
    _name = "quote.signing"
    _description = "Quote Signing Audit Record"
    _order = "signed_at desc"

    sale_order_id = fields.Many2one("sale.order", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one("res.company", related="sale_order_id.company_id", store=True)

    # Signer identity
    signer_name = fields.Char(required=True, readonly=True)
    signer_email = fields.Char(required=True, readonly=True)

    # Timing & provenance
    signed_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    ip_address = fields.Char(readonly=True)
    user_agent = fields.Char(readonly=True)

    # Document integrity
    document_hash = fields.Char(
        "Document Hash (SHA-256)",
        readonly=True,
        help="SHA-256 hash of the quote PDF bytes at time of signing.",
    )
    document_version = fields.Char(readonly=True, help="sale.order write_date at signing time.")
    terms_version_id = fields.Many2one("quote.terms.version", readonly=True)

    # Signature
    signature_data = fields.Text(
        "Signature (base64 PNG)",
        readonly=True,
        help="Base64-encoded PNG of the drawn/typed signature.",
    )
    signature_type = fields.Selection(
        [("drawn", "Drawn"), ("typed", "Typed")],
        readonly=True,
        default="drawn",
    )

    # Acceptance evidence
    terms_accepted = fields.Boolean("Terms Explicitly Accepted", readonly=True, default=False)
    payment_obligation_accepted = fields.Boolean(
        "Payment Obligation Accepted", readonly=True, default=False
    )

    # Event log
    event_log = fields.Text(
        "Event Log (JSON)",
        readonly=True,
        help="Ordered list of timestamped events: page-load, terms-open, checkbox-checked, signed.",
    )

    # Generated PDF
    signed_pdf_attachment_id = fields.Many2one(
        "ir.attachment", "Signed PDF", readonly=True, ondelete="set null"
    )

    def write(self, vals):
        raise UserError("Signing audit records are immutable.")

    def unlink(self):
        raise UserError("Signing audit records cannot be deleted.")

    @api.model
    def create_signing_record(
        self,
        *,
        sale_order,
        signer_name: str,
        signer_email: str,
        ip_address: str = "",
        user_agent: str = "",
        document_hash: str = "",
        signature_data: str = "",
        signature_type: str = "drawn",
        terms_accepted: bool = False,
        payment_obligation_accepted: bool = False,
        terms_version=None,
        events: list | None = None,
    ) -> "QuoteSigning":
        """Create a signing audit record. All validation must be done by the caller."""
        record = self.sudo().create(
            {
                "sale_order_id": sale_order.id,
                "signer_name": signer_name,
                "signer_email": signer_email,
                "signed_at": fields.Datetime.now(),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "document_hash": document_hash,
                "document_version": str(sale_order.write_date),
                "terms_version_id": terms_version.id if terms_version else False,
                "signature_data": signature_data,
                "signature_type": signature_type,
                "terms_accepted": terms_accepted,
                "payment_obligation_accepted": payment_obligation_accepted,
                "event_log": json.dumps(events or []),
            }
        )
        self.env["platform.audit.log"].sudo().log(
            "signing_signed",
            res_model=self._name,
            res_id=record.id,
            res_name=sale_order.name,
            summary=(
                f"Quote '{sale_order.name}' signed by {signer_name} <{signer_email}> "
                f"from IP {ip_address}"
            ),
            details={
                "signer_name": signer_name,
                "signer_email": signer_email,
                "document_hash": document_hash,
                "terms_accepted": terms_accepted,
                "payment_obligation_accepted": payment_obligation_accepted,
            },
            severity="warning",
        )
        return record

    @staticmethod
    def compute_document_hash(pdf_bytes: bytes) -> str:
        """SHA-256 hash of the PDF bytes."""
        return hashlib.sha256(pdf_bytes).hexdigest()
