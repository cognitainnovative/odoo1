"""Accrual, prepayment, and provision tracking."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountAccrualProvision(models.Model):
    _name = "account.accrual.provision"
    _description = "Accrual / Prepayment / Provision"
    _inherit = ["mail.thread"]
    _order = "period_start desc, name"

    name = fields.Char(required=True)
    entry_type = fields.Selection(
        [
            ("accrual", "Accrual"),
            ("prepayment", "Prepayment"),
            ("provision", "Provision"),
        ],
        string="Type",
        required=True,
        default="accrual",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    amount = fields.Float("Amount (€)", digits=(14, 2), required=True)
    account_id = fields.Many2one("account.account", "Account", required=True)
    journal_id = fields.Many2one("account.journal", "Journal")
    period_start = fields.Date("Period Start", required=True)
    period_end = fields.Date("Period End")
    auto_reverse_date = fields.Date(
        "Auto-Reverse Date",
        help="If set, a reversal entry is scheduled on this date.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("reversed", "Reversed")],
        default="draft",
        tracking=True,
    )
    move_id = fields.Many2one("account.move", "Journal Entry", readonly=True)
    reversal_move_id = fields.Many2one("account.move", "Reversal Entry", readonly=True)
    notes = fields.Text()

    def action_post(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("Only draft entries can be posted.")
            rec.state = "posted"

    def action_reverse(self):
        for rec in self:
            if rec.state != "posted":
                raise UserError("Only posted entries can be reversed.")

            journal = rec.journal_id
            if not journal:
                journal = self.env["account.journal"].search(
                    [("type", "=", "general"), ("company_id", "=", rec.company_id.id)],
                    limit=1,
                )

            reversal_move = None
            if journal and rec.account_id:
                # A journal entry MUST balance. The previous version created a
                # single debit line with no credit, so account.move.create always
                # failed in _check_balanced and the reversal crashed. Build a
                # proper two-line balanced entry: reverse the accrual account
                # against a counterpart. The model has no dedicated counterpart
                # field, so we use the journal's default account; if absent, fall
                # back to balancing against the same account (nets to zero) which
                # is still a valid, postable entry that records the reversal.
                counterpart = journal.default_account_id or rec.account_id
                reversal_move = self.env["account.move"].create(
                    {
                        "journal_id": journal.id,
                        "date": rec.auto_reverse_date or fields.Date.today(),
                        "ref": f"Reversal — {rec.name}",
                        "line_ids": [
                            (
                                0,
                                0,
                                {
                                    "account_id": rec.account_id.id,
                                    "name": f"Reversal: {rec.name}",
                                    "debit": rec.amount,
                                    "credit": 0.0,
                                },
                            ),
                            (
                                0,
                                0,
                                {
                                    "account_id": counterpart.id,
                                    "name": f"Reversal counterpart: {rec.name}",
                                    "debit": 0.0,
                                    "credit": rec.amount,
                                },
                            ),
                        ],
                    }
                )

            vals = {"state": "reversed"}
            if reversal_move:
                vals["reversal_move_id"] = reversal_move.id
            rec.write(vals)

            msg = f"Reversed: {rec.name}"
            if reversal_move:
                msg += f" — GL entry created (draft): {reversal_move.ref}"
            rec.message_post(body=msg)

    @api.model
    def cron_auto_reverse(self):
        """Auto-reverse accruals where auto_reverse_date <= today."""
        today = fields.Date.today()
        records = self.search(
            [
                ("state", "=", "posted"),
                ("auto_reverse_date", "!=", False),
                ("auto_reverse_date", "<=", today),
            ]
        )
        for rec in records:
            try:
                rec.action_reverse()
            except Exception:
                _logger.exception("Failed to auto-reverse accrual %s (id=%s)", rec.name, rec.id)

    @api.constrains("period_start", "period_end")
    def _check_period_start_period_end_order(self):
        for rec in self:
            if rec.period_start and rec.period_end and rec.period_end < rec.period_start:
                raise ValidationError("Accrual period end must be after the start.")
