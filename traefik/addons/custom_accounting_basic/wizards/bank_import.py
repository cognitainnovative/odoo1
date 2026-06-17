"""Bank statement import wizard — CSV, MT940, CAMT.053."""

import base64
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BankStatementImportWizard(models.TransientModel):
    _name = "bank.statement.import.wizard"
    _description = "Bank Statement Import"

    journal_id = fields.Many2one(
        "account.journal",
        "Bank Journal",
        required=True,
        domain="[('type', '=', 'bank')]",
        default=lambda self: self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        ),
    )
    file_format = fields.Selection(
        [
            ("csv", "CSV (comma-separated)"),
            ("csv_semicolon", "CSV (semicolon-separated)"),
            ("mt940", "MT940 / SWIFT"),
            ("camt053", "CAMT.053 (ISO 20022 XML)"),
        ],
        string="File Format",
        required=True,
        default="csv",
    )
    statement_file = fields.Binary("Statement File", required=True)
    statement_filename = fields.Char("Filename")

    # Results
    import_count = fields.Integer("Lines Imported", readonly=True)
    skip_count = fields.Integer("Lines Skipped (duplicates)", readonly=True)
    statement_id = fields.Many2one("account.bank.statement", "Created Statement", readonly=True)

    def action_import(self):
        """Parse the uploaded file and create a bank statement."""
        self.ensure_one()
        if not self.statement_file:
            raise UserError("Please upload a file.")

        raw = base64.b64decode(self.statement_file)
        transactions = self._parse(raw)

        if not transactions:
            raise UserError(
                "No transactions found in the file. " "Please check the file format and content."
            )

        # De-duplicate against existing statement lines
        existing_refs = (
            self.env["account.bank.statement.line"]
            .sudo()
            .search_read(
                [("journal_id", "=", self.journal_id.id)],
                ["unique_import_id"],
            )
        )
        existing_ids = {r["unique_import_id"] for r in existing_refs if r["unique_import_id"]}

        new_txns = [t for t in transactions if t.get("unique_import_id") not in existing_ids]
        skip_count = len(transactions) - len(new_txns)

        if not new_txns:
            self.write({"import_count": 0, "skip_count": skip_count})
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Nothing to Import",
                    "message": f"All {skip_count} transactions already exist.",
                    "type": "warning",
                },
            }

        # Create bank statement
        stmt_name = f"{self.journal_id.name} — {self.statement_filename or 'import'}"
        statement = self.env["account.bank.statement"].create(
            {"name": stmt_name, "journal_id": self.journal_id.id}
        )

        for txn in new_txns:
            self.env["account.bank.statement.line"].create(
                {
                    "statement_id": statement.id,
                    "journal_id": self.journal_id.id,
                    "date": txn["date"],
                    "amount": txn["amount"],
                    "payment_ref": txn.get("payment_ref") or txn.get("ref") or "/",
                    "partner_name": txn.get("partner_name") or "",
                    "unique_import_id": txn.get("unique_import_id") or "",
                }
            )

        self.write(
            {
                "import_count": len(new_txns),
                "skip_count": skip_count,
                "statement_id": statement.id,
            }
        )

        return {
            "type": "ir.actions.act_window",
            "name": "Imported Statement",
            "res_model": "account.bank.statement",
            "res_id": statement.id,
            "view_mode": "form",
        }

    def _parse(self, raw: bytes) -> list[dict]:
        from ..lib.bank_parsers import parse_camt053, parse_csv, parse_mt940

        if self.file_format == "csv":
            return parse_csv(raw, delimiter=",")
        if self.file_format == "csv_semicolon":
            return parse_csv(raw, delimiter=";")
        if self.file_format == "mt940":
            return parse_mt940(raw)
        if self.file_format == "camt053":
            return parse_camt053(raw)
        return []
