"""Extend account.bank.statement.line with AI reconciliation suggestions."""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    # AI reconciliation
    unique_import_id = fields.Char(
        "Unique Import ID",
        index=True,
        copy=False,
        readonly=True,
        help="De-duplication key from the bank import parser.",
    )
    ai_match_confidence = fields.Float(
        "AI Match Confidence", digits=(4, 2), readonly=True, default=0.0
    )
    ai_match_invoice_id = fields.Many2one(
        "account.move", "AI-Suggested Invoice", readonly=True, ondelete="set null"
    )
    ai_match_reason = fields.Text("AI Match Reason", readonly=True)
    ai_match_done = fields.Boolean("AI Match Run", default=False, readonly=True)

    def action_suggest_ai_match(self):
        """Run AI reconciliation suggestion for this line."""
        for line in self:
            line._do_ai_suggest()

    def _do_ai_suggest(self):
        """Score open invoices and optionally ask AI to confirm the best match."""
        from ..lib.reconciliation import build_ai_reconciliation_prompt, score_candidates

        self.ensure_one()

        # Find open invoices/bills in the right direction
        move_type = "out_invoice" if self.amount > 0 else "in_invoice"
        open_moves = self.env["account.move"].search_read(
            [
                ("move_type", "=", move_type),
                ("payment_state", "in", ("not_paid", "partial")),
                ("state", "=", "posted"),
                ("company_id", "=", self.company_id.id),
            ],
            fields=["id", "name", "amount_residual", "partner_id", "ref", "invoice_date_due"],
            limit=50,
        )
        # Enrich with partner name
        for m in open_moves:
            partner = self.env["res.partner"].browse(m.get("partner_id") and m["partner_id"][0])
            m["partner_name"] = partner.name or ""
            m["partner_iban"] = partner.bank_ids[:1].acc_number if partner.bank_ids else ""

        from datetime import date as _date

        stmt_date = self.date if isinstance(self.date, _date) else _date.today()

        candidates = score_candidates(
            stmt_amount=self.amount,
            stmt_ref=self.payment_ref or "",
            stmt_partner=self.partner_name or (self.partner_id.name or ""),
            stmt_date=stmt_date,
            candidates=open_moves,
        )

        best = candidates[0] if candidates else None
        ai_reason = ""

        if best and best.confidence >= 0.60:
            # High enough to suggest without AI call
            ai_reason = " | ".join(best.reasons)
        elif best and best.confidence >= 0.30:
            # Ask AI to confirm
            prompt = build_ai_reconciliation_prompt(
                stmt_amount=self.amount,
                stmt_ref=self.payment_ref or "",
                stmt_partner=self.partner_name or "",
                stmt_date=stmt_date,
                top_candidates=candidates[:3],
            )
            result = self.env["ai.service"].call(prompt)
            if result["ok"]:
                ai_content = result["content"].strip()
                # Check if AI confirmed the best candidate
                if best.move_name.lower() in ai_content.lower():
                    ai_reason = f"AI confirmed: {ai_content[:200]}"
                    best.confidence = min(best.confidence + 0.20, 1.0)
                else:
                    best = None

        vals = {
            "ai_match_done": True,
            "ai_match_confidence": best.confidence if best else 0.0,
            "ai_match_invoice_id": best.move_id if best else False,
            "ai_match_reason": ai_reason if best else "No match found",
        }
        self.write(vals)

    def action_confirm_ai_match(self):
        """Accept the AI suggestion and reconcile the line."""
        self.ensure_one()
        if not self.ai_match_invoice_id:
            return
        if not self.partner_id and self.ai_match_invoice_id.partner_id:
            self.write({"partner_id": self.ai_match_invoice_id.partner_id.id})
        self.env["accounting.audit.log"].sudo().log(
            event_type="ai_match_accepted",
            res_model="account.bank.statement.line",
            res_id=self.id,
            document_ref=self.payment_ref,
            details=(
                f"AI match confirmed — Invoice {self.ai_match_invoice_id.name}, "
                f"confidence {self.ai_match_confidence:.0%}, "
                f"amount {self.amount:.2f}"
            ),
        )
