"""Audit-file export — CSV/XML export of all journal entries for tax audit."""

import base64
import csv
import io
import logging
from xml.etree import ElementTree as ET

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountAuditExport(models.TransientModel):
    _name = "account.audit.export.wizard"
    _description = "Audit File Export Wizard"

    date_from = fields.Date("From Date", required=True)
    date_to = fields.Date("To Date", required=True)
    export_format = fields.Selection(
        [("csv", "CSV (accountant-friendly)"), ("xml", "XML (structured)")],
        default="csv",
        required=True,
    )
    include_drafts = fields.Boolean("Include Draft Entries", default=False)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    def action_export(self):
        """Generate the audit file."""
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if not self.include_drafts:
            domain.append(("state", "=", "posted"))

        moves = self.env["account.move"].search(domain, order="date, name")
        lines = []
        for move in moves:
            for line in move.line_ids:
                lines.append(
                    {
                        "entry_ref": move.name or "",
                        "entry_date": str(move.date),
                        "journal": move.journal_id.name or "",
                        "account_code": line.account_id.code or "",
                        "account_name": line.account_id.name or "",
                        "partner": line.partner_id.name or "",
                        "description": line.name or "",
                        "debit": line.debit,
                        "credit": line.credit,
                        "state": move.state,
                    }
                )

        if self.export_format == "csv":
            content = self._build_csv(lines)
            filename = f"audit_export_{self.date_from}_{self.date_to}.csv"
            mimetype = "text/csv"
        else:
            content = self._build_xml(lines)
            filename = f"audit_export_{self.date_from}_{self.date_to}.xml"
            mimetype = "application/xml"

        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(content),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": mimetype,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    @staticmethod
    def _build_csv(lines: list[dict]) -> bytes:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "entry_ref",
                "entry_date",
                "journal",
                "account_code",
                "account_name",
                "partner",
                "description",
                "debit",
                "credit",
                "state",
            ],
        )
        writer.writeheader()
        writer.writerows(lines)
        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def _build_xml(lines: list[dict]) -> bytes:
        root = ET.Element("AuditFile")
        entries_el = ET.SubElement(root, "JournalEntries")
        for line in lines:
            entry_el = ET.SubElement(entries_el, "Entry")
            for key, val in line.items():
                el = ET.SubElement(entry_el, key)
                el.text = str(val)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
