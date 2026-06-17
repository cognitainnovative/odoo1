"""Invoice CSV/Excel export wizard — exports outgoing or incoming invoices for a date range."""

import base64
import csv
import io
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_MOVE_TYPES = {
    "outgoing": ["out_invoice", "out_receipt"],
    "incoming": ["in_invoice", "in_receipt"],
    "credit_notes": ["out_refund", "in_refund"],
    "all": ["out_invoice", "in_invoice", "out_refund", "in_refund", "out_receipt", "in_receipt"],
}


class InvoiceExportWizard(models.TransientModel):
    _name = "invoice.export.wizard"
    _description = "Invoice CSV Export"

    invoice_type = fields.Selection(
        [
            ("outgoing", "Outgoing Invoices (Customer)"),
            ("incoming", "Incoming Bills (Supplier)"),
            ("credit_notes", "Credit Notes"),
            ("all", "All"),
        ],
        string="Invoice Type",
        required=True,
        default="outgoing",
    )
    date_from = fields.Date(
        "Date From", required=True, default=lambda self: self._default_date_from()
    )
    date_to = fields.Date("Date To", required=True, default=fields.Date.today)
    state_filter = fields.Selection(
        [
            ("all", "All States"),
            ("posted", "Posted Only"),
            ("draft", "Draft Only"),
        ],
        string="Status",
        required=True,
        default="posted",
    )

    # Result
    export_file = fields.Binary("Download CSV", readonly=True)
    export_filename = fields.Char(readonly=True)
    export_done = fields.Boolean(readonly=True, default=False)
    export_count = fields.Integer("Lines Exported", readonly=True)

    @staticmethod
    def _default_date_from():
        from dateutil.relativedelta import relativedelta

        today = fields.Date.today()
        return today - relativedelta(months=1)

    def action_export(self):
        """Build the CSV and attach it to the wizard record."""
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError("Date To must be on or after Date From.")

        domain = [
            ("move_type", "in", _MOVE_TYPES[self.invoice_type]),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
            ("company_id", "=", self.env.company.id),
        ]
        if self.state_filter != "all":
            domain.append(("state", "=", self.state_filter))

        moves = self.env["account.move"].search(domain, order="invoice_date, name")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Invoice Number",
                "Type",
                "State",
                "Invoice Date",
                "Due Date",
                "Partner",
                "Partner VAT",
                "Reference",
                "Currency",
                "Amount Untaxed",
                "Amount Tax",
                "Amount Total",
                "Amount Residual",
                "Payment State",
                "AI Extracted",
                "Reminder Sent",
            ]
        )

        for move in moves:
            writer.writerow(
                [
                    move.name or "/",
                    move.move_type,
                    move.state,
                    move.invoice_date or "",
                    move.invoice_date_due or "",
                    move.partner_id.name if move.partner_id else "",
                    move.partner_id.vat if move.partner_id else "",
                    move.ref or "",
                    move.currency_id.name if move.currency_id else "EUR",
                    move.amount_untaxed,
                    move.amount_tax,
                    move.amount_total,
                    move.amount_residual,
                    move.payment_state or "",
                    "Yes" if move.ai_extracted else "No",
                    "Yes" if move.reminder_sent else "No",
                ]
            )

        csv_bytes = output.getvalue().encode("utf-8-sig")  # UTF-8 BOM for Excel compatibility
        filename = f"invoices_{self.invoice_type}_{self.date_from}_{self.date_to}.csv"

        self.write(
            {
                "export_file": base64.b64encode(csv_bytes),
                "export_filename": filename,
                "export_done": True,
                "export_count": len(moves),
            }
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
