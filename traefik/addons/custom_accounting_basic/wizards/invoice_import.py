"""Incoming invoice import wizard — AI OCR extraction from uploaded PDF/image."""

import base64
import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class InvoiceImportWizard(models.TransientModel):
    _name = "invoice.import.wizard"
    _description = "Incoming Invoice Import (AI OCR)"

    invoice_file = fields.Binary("Invoice File (PDF / Image)", required=True)
    invoice_filename = fields.Char("Filename")

    # ── Extracted header fields (editable before creating) ──────────────────
    supplier_name = fields.Char("Supplier Name")
    invoice_number = fields.Char("Invoice Number")
    invoice_date = fields.Date("Invoice Date")
    due_date = fields.Date("Due Date")
    amount_untaxed = fields.Float("Amount Excl. Tax", digits=(16, 2))
    amount_tax = fields.Float("Tax Amount", digits=(16, 2))
    amount_total = fields.Float("Total Amount", digits=(16, 2))
    currency_name = fields.Char("Currency", default="EUR")
    iban = fields.Char("Supplier IBAN")
    payment_reference = fields.Char("Payment Reference")
    description = fields.Text("Invoice Description")

    # ── Line items extracted by AI ──────────────────────────────────────────
    line_items_json = fields.Text(
        "Extracted Line Items (JSON)",
        readonly=True,
        help="JSON array from AI extraction. Parsed into invoice lines on creation.",
    )

    # ── Suggested journal/account from supplier history ─────────────────────
    suggested_account_id = fields.Many2one(
        "account.account",
        "Suggested Expense Account",
        readonly=True,
        help="Account used on the supplier's most recent bill — proposed for booking.",
    )

    # ── AI extraction status ─────────────────────────────────────────────────
    extraction_done = fields.Boolean(readonly=True, default=False)
    extraction_confidence = fields.Float(readonly=True, digits=(4, 2))
    extraction_raw = fields.Text("Raw AI Response", readonly=True)

    # ── Approval state ───────────────────────────────────────────────────────
    approval_state = fields.Selection(
        [
            ("extracted", "Extracted — Pending Review"),
            ("approved", "Approved for Booking"),
        ],
        string="Approval",
        default="extracted",
        readonly=True,
    )

    # ── Result ───────────────────────────────────────────────────────────────
    created_invoice_id = fields.Many2one("account.move", readonly=True)

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_extract(self):
        """Use AI to extract invoice fields from the uploaded file."""
        self.ensure_one()
        if not self.invoice_file:
            raise UserError("Please upload an invoice file.")

        raw_bytes = base64.b64decode(self.invoice_file)
        filename = self.invoice_filename or ""

        extracted_text = self._extract_text(raw_bytes, filename)
        if not extracted_text:
            extracted_text = (
                f"[File: {filename}, {len(raw_bytes)} bytes — text extraction not available]"
            )

        prompt = (
            "Extract invoice data from the following text and return JSON only.\n"
            "Required fields: supplier_name, invoice_number, invoice_date (YYYY-MM-DD), "
            "due_date (YYYY-MM-DD), amount_total (float), amount_tax (float), "
            "iban (if present), payment_reference (if present), currency (default EUR).\n"
            "Optional: line_items as a JSON array of objects with keys: "
            "description (string), quantity (float), unit_price (float), vat_rate (float).\n"
            "Return ONLY valid JSON, no explanation.\n\n"
            f"Invoice text:\n{extracted_text[:3000]}"
        )

        result = self.env["ai.service"].call(
            prompt,
            template_code=None,
            res_model=self._name,
        )

        if not result["ok"]:
            _logger.warning("Invoice extraction AI call failed: %s", result["error"])
            self.write({"extraction_done": True, "extraction_confidence": 0.0})
            return self._show_form()

        raw_content = result["content"]
        extracted = {}
        confidence = 0.0

        try:
            clean = raw_content.strip()
            if clean.startswith("```"):
                parts = clean.split("```")
                clean = parts[1] if len(parts) > 1 else parts[-1]
                clean = clean.lstrip("json").strip()
            extracted = json.loads(clean)
            confidence = 0.75
        except (json.JSONDecodeError, ValueError):
            _logger.warning("Could not parse AI JSON: %s", raw_content[:200])

        vals = {
            "extraction_done": True,
            "extraction_confidence": confidence,
            "extraction_raw": raw_content[:2000],
            "approval_state": "extracted",
        }
        if extracted:
            vals.update(
                {
                    "supplier_name": extracted.get("supplier_name") or self.supplier_name,
                    "invoice_number": extracted.get("invoice_number") or self.invoice_number,
                    "invoice_date": extracted.get("invoice_date") or self.invoice_date,
                    "due_date": extracted.get("due_date") or self.due_date,
                    "amount_total": float(extracted.get("amount_total") or self.amount_total or 0),
                    "amount_tax": float(extracted.get("amount_tax") or self.amount_tax or 0),
                    "iban": extracted.get("iban") or self.iban,
                    "payment_reference": extracted.get("payment_reference")
                    or self.payment_reference,
                    "currency_name": extracted.get("currency") or "EUR",
                }
            )
            # Store raw line items JSON for later use in invoice creation
            raw_lines = extracted.get("line_items")
            if raw_lines and isinstance(raw_lines, list):
                vals["line_items_json"] = json.dumps(raw_lines)

        self.write(vals)

        # Suggest expense account from supplier history
        self._suggest_account()

        # Log extraction event
        self.env["accounting.audit.log"].sudo().log(
            event_type="ai_extraction",
            res_model=self._name,
            res_id=self.id,
            document_ref=extracted.get("invoice_number") or filename,
            details=(
                f"AI extraction — supplier: {extracted.get('supplier_name', '?')}, "
                f"confidence: {confidence:.0%}"
            ),
        )

        return self._show_form()

    def action_approve(self):
        """Approve this invoice extraction for booking (accounting manager step)."""
        self.ensure_one()
        if not self.extraction_done:
            raise UserError("Run AI extraction first before approving.")
        self.write({"approval_state": "approved"})
        self.env["accounting.audit.log"].sudo().log(
            event_type="approval",
            res_model=self._name,
            res_id=self.id,
            document_ref=self.invoice_number or self.invoice_filename,
            details=(
                f"Approved by {self.env.user.name} — "
                f"supplier: {self.supplier_name}, total: {self.amount_total:.2f}"
            ),
        )
        return self._show_form()

    def action_create_invoice(self):
        """Create a vendor bill draft from the extracted + approved data."""
        self.ensure_one()

        if self.approval_state != "approved":
            if not self.env.user.has_group("account.group_account_manager"):
                raise UserError(
                    "This invoice requires approval before booking. "
                    "Click 'Approve for Booking' or ask your accounting manager."
                )

        partner = (
            self.env["res.partner"].search([("name", "ilike", self.supplier_name)], limit=1)
            if self.supplier_name
            else self.env["res.partner"]
        )

        journal = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )

        move_vals = {
            "move_type": "in_invoice",
            "partner_id": partner.id if partner else False,
            "invoice_date": self.invoice_date,
            "invoice_date_due": self.due_date,
            "ref": self.invoice_number,
            "journal_id": journal.id if journal else False,
            "ai_extracted": True,
            "extraction_confidence": self.extraction_confidence,
            "import_reference": self.invoice_number or self.invoice_filename,
            "invoice_line_ids": self._build_invoice_lines(),
        }

        move = self.env["account.move"].create(move_vals)
        self.created_invoice_id = move

        if self.invoice_file:
            self.env["ir.attachment"].create(
                {
                    "name": self.invoice_filename or "invoice.pdf",
                    "type": "binary",
                    "datas": self.invoice_file,
                    "res_model": "account.move",
                    "res_id": move.id,
                }
            )

        # Detect duplicates automatically
        move.action_detect_duplicates()

        # Log creation
        self.env["accounting.audit.log"].sudo().log(
            event_type="ai_extraction",
            res_model="account.move",
            res_id=move.id,
            document_ref=move.ref,
            details=(
                f"Vendor bill created from AI extraction — "
                f"confidence: {self.extraction_confidence:.0%}, "
                f"approval: {self.approval_state}"
            ),
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _build_invoice_lines(self) -> list:
        """Build invoice_line_ids command list from extracted line items or catch-all."""
        lines = []
        account_id = self.suggested_account_id.id if self.suggested_account_id else False
        # An invoice line MUST have an account (Odoo 19 enforces this at DB level).
        # If no account was suggested from supplier history, fall back to a sane
        # default expense account so AI-extracted bills always post a valid,
        # balanced journal entry rather than crashing on a NULL account_id.
        if not account_id:
            account_id = self._default_expense_account_id()

        if self.line_items_json:
            try:
                items = json.loads(self.line_items_json)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    desc = item.get("description") or "Invoice line"
                    qty = float(item.get("quantity") or 1)
                    price = float(item.get("unit_price") or 0)
                    lines.append(
                        (
                            0,
                            0,
                            {
                                "name": desc,
                                "quantity": qty,
                                "price_unit": price,
                                "account_id": account_id,
                            },
                        )
                    )
            except (json.JSONDecodeError, ValueError):
                _logger.warning("Could not parse line_items_json — falling back to catch-all")

        if not lines and self.amount_total and self.amount_total > 0:
            net = self.amount_total - self.amount_tax
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": self.description or f"Invoice {self.invoice_number or ''}",
                        "price_unit": max(net, self.amount_total),
                        "quantity": 1,
                        "account_id": account_id,
                    },
                )
            )

        return lines

    def _default_expense_account_id(self) -> int | bool:
        """Pick a default expense account for AI-extracted bill lines.

        Order: (1) the purchase journal's default account if set, (2) the first
        expense-type account in the company. Returns False only if the chart of
        accounts has no expense account at all (extremely unlikely).
        """
        company = self.env.company
        journal = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1
        )
        if journal and journal.default_account_id:
            return journal.default_account_id.id
        expense = self.env["account.account"].search([("account_type", "=", "expense")], limit=1)
        return expense.id if expense else False

    def _suggest_account(self):
        """Propose expense account from supplier's most recent posted bill."""
        if not self.supplier_name:
            return
        partner = self.env["res.partner"].search([("name", "ilike", self.supplier_name)], limit=1)
        if not partner:
            return
        last_bill = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("partner_id", "=", partner.id),
                ("state", "=", "posted"),
            ],
            order="invoice_date desc",
            limit=1,
        )
        if last_bill and last_bill.invoice_line_ids:
            acc = last_bill.invoice_line_ids.filtered("account_id")[:1].account_id
            if acc:
                self.suggested_account_id = acc

    def _extract_text(self, raw_bytes: bytes, filename: str) -> str:
        """Extract text from PDF or image; gracefully degrades if libs not available."""
        try:
            import io

            import pdfplumber

            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
        except Exception:
            pass
        try:
            return raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _show_form(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
