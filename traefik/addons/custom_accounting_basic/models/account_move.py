"""Extend account.move (invoice/bill) with import tracking, payment reminders, audit log."""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # ── Import / OCR tracking ─────────────────────────────────────────────────
    ai_extracted = fields.Boolean("Imported via AI / OCR", default=False, readonly=True)
    extraction_confidence = fields.Float(
        "Extraction Confidence",
        digits=(4, 2),
        readonly=True,
        help="0–1 score from AI extraction. 1 = high confidence.",
    )
    import_reference = fields.Char(
        "Import Reference",
        help="Original document number or file name from which this was extracted.",
    )
    # Duplicate detection
    duplicate_move_ids = fields.Many2many(
        "account.move",
        "account_move_duplicate_rel",
        "move_id",
        "duplicate_id",
        "Potential Duplicates",
        domain="[('move_type', '=', move_type)]",
    )
    duplicate_count = fields.Integer("Duplicate Count", compute="_compute_duplicate_count")

    # ── Payment link (Mollie placeholder) ────────────────────────────────────
    mollie_payment_link = fields.Char(
        "Payment Link (Mollie)",
        copy=False,
        help=(
            "Placeholder for a Mollie payment link. "
            "Populate via the Mollie integration once the provider connection is configured. "
            "This is a simple/advanced electronic payment — requires Mollie API credentials."
        ),
    )

    # ── Pro forma ─────────────────────────────────────────────────────────────
    is_proforma = fields.Boolean(
        "Pro Forma Invoice",
        default=False,
        copy=False,
        help=(
            "Mark this draft invoice as a Pro Forma. "
            "A Pro Forma is a non-binding price indication. "
            "Use 'Send Pro Forma' to email/print; it will not be posted. "
            "Remove the flag and post when ready to issue the final invoice."
        ),
    )

    # ── Payment reminders ─────────────────────────────────────────────────────
    reminder_sent = fields.Boolean("Payment Reminder Sent", default=False, readonly=True)
    reminder_sent_date = fields.Datetime("Reminder Sent On", readonly=True)
    days_overdue = fields.Integer("Days Overdue", compute="_compute_days_overdue")

    @api.depends("duplicate_move_ids")
    def _compute_duplicate_count(self):
        for rec in self:
            rec.duplicate_count = len(rec.duplicate_move_ids)

    @api.depends("invoice_date_due", "payment_state")
    def _compute_days_overdue(self):
        today = fields.Date.today()
        for rec in self:
            if (
                rec.invoice_date_due
                and rec.payment_state not in ("paid", "reversed")
                and rec.state == "posted"
            ):
                delta = (today - rec.invoice_date_due).days
                rec.days_overdue = max(0, delta)
            else:
                rec.days_overdue = 0

    def action_detect_duplicates(self):
        """Detect potential duplicates based on partner + amount + date."""
        for move in self:
            if not move.partner_id or not move.amount_total:
                continue
            dupes = self.search(
                [
                    ("id", "!=", move.id),
                    ("move_type", "=", move.move_type),
                    ("partner_id", "=", move.partner_id.id),
                    ("amount_total", "=", move.amount_total),
                    ("state", "!=", "cancel"),
                ],
                limit=10,
            )
            move.duplicate_move_ids = dupes

    def action_send_payment_reminder(self):
        """Send a payment reminder for overdue invoices."""
        for move in self:
            if move.days_overdue <= 0 or not move.partner_id:
                continue
            # Create a simple chatter note as reminder (email can be added in M16)
            move.message_post(
                body=(
                    f"<b>Payment Reminder</b><br/>"
                    f"Invoice {move.name} is {move.days_overdue} day(s) overdue. "
                    f"Amount: €{move.amount_residual:.2f}.<br/>"
                    f"Please arrange payment at your earliest convenience."
                ),
                subtype_id=self.env.ref("mail.mt_comment").id,
                partner_ids=move.partner_id.ids,
            )
            move.write({"reminder_sent": True, "reminder_sent_date": fields.Datetime.now()})
            self.env["accounting.audit.log"].sudo().log(
                event_type="payment_reminder_sent",
                res_model="account.move",
                res_id=move.id,
                document_ref=move.name,
                details=(
                    f"Reminder sent for {move.name} — "
                    f"{move.days_overdue} day(s) overdue, "
                    f"€{move.amount_residual:.2f} outstanding"
                ),
            )

    def action_open_payment_link(self):
        """Open the Mollie payment link in a new browser tab (placeholder)."""
        self.ensure_one()
        if not self.mollie_payment_link:
            return
        return {
            "type": "ir.actions.act_url",
            "url": self.mollie_payment_link,
            "target": "new",
        }

    def action_send_proforma(self):
        """Generate a pro forma PDF and open the send-by-email dialog."""
        self.ensure_one()
        if self.state != "draft":
            from odoo.exceptions import UserError

            raise UserError("Pro forma can only be sent for draft invoices.")
        report = self.env.ref(
            "custom_accounting_basic.action_report_proforma_invoice",
            raise_if_not_found=False,
        )
        if report:
            return report.report_action(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Pro Forma",
                "message": "Pro forma report not found. Please check the addon installation.",
                "type": "warning",
            },
        }

    def action_remove_proforma(self):
        """Clear the pro forma flag so the invoice can be posted normally."""
        self.write({"is_proforma": False})

    def action_post(self):
        result = super().action_post()
        for move in self.filtered(lambda m: m.state == "posted"):
            etype = (
                "credit_note_created"
                if move.move_type in ("out_refund", "in_refund")
                else "invoice_posted"
            )
            self.env["accounting.audit.log"].sudo().log(
                event_type=etype,
                res_model="account.move",
                res_id=move.id,
                document_ref=move.name,
                details=(
                    f"Posted {move.move_type} for "
                    f"{move.partner_id.name or 'unknown'} — "
                    f"€{move.amount_total:.2f}"
                ),
            )
        return result

    def action_ai_extract_review(self):
        """Open the extraction review panel (placeholder — M13 email_ai adds full UI)."""
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "AI Extraction",
                "message": (
                    f"This invoice was extracted with {self.extraction_confidence:.0%} confidence. "
                    "Please review all fields before posting."
                ),
                "type": "info",
            },
        }
