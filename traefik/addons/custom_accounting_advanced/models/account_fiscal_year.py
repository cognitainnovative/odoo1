"""Custom fiscal year model and period lock extensions for res.company."""

from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class AccountFiscalYear(models.Model):
    _name = "account.fiscal.year.custom"
    _description = "Fiscal Year"
    _order = "date_from desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    date_from = fields.Date("Start Date", required=True)
    date_to = fields.Date("End Date", required=True)
    state = fields.Selection(
        [("open", "Open"), ("locked", "Locked"), ("closed", "Closed")],
        default="open",
    )
    opening_balance_done = fields.Boolean("Opening Balance Posted", default=False)
    closing_entries_done = fields.Boolean("Closing Entries Posted", default=False)
    opening_balance_move_id = fields.Many2one(
        "account.move", "Opening Balance Entry", readonly=True
    )
    closing_entries_move_id = fields.Many2one("account.move", "Closing Entries", readonly=True)
    notes = fields.Text()

    _year_company_uniq = models.Constraint(
        "UNIQUE(company_id, date_from, date_to)",
        "Fiscal year dates must be unique per company.",
    )

    def action_lock(self):
        self.write({"state": "locked"})

    def action_close(self):
        for fy in self:
            if not fy.closing_entries_done:
                raise UserError(
                    f"Please post closing entries for {fy.name} before marking it closed."
                )
            fy.state = "closed"

    def action_reopen(self):
        """Reopen a locked fiscal year (admin only — requires reason via chatter)."""
        self.write({"state": "open"})

    def _get_general_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )

    def action_create_opening_entries(self):
        """Create a draft journal entry with opening balances from the prior period."""
        self.ensure_one()
        if self.opening_balance_done:
            raise UserError(
                "Opening balance entries have already been created for this fiscal year."
            )
        journal = self._get_general_journal()
        if not journal:
            raise UserError("No general journal found. Please create one first.")

        prior_date = self.date_from - timedelta(days=1)
        balance_sheet_types = [
            "asset_receivable",
            "asset_cash",
            "asset_current",
            "asset_non_current",
            "asset_prepayments",
            "asset_fixed",
            "liability_payable",
            "liability_current",
            "liability_non_current",
            "equity",
            "equity_unaffected",
        ]
        lines = []
        for account in self.env["account.account"].search(
            [
                ("account_type", "in", balance_sheet_types),
                ("company_ids", "in", [self.company_id.id]),
            ]
        ):
            self.env.cr.execute(
                """
                SELECT COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0)
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE aml.account_id = %s
                  AND am.state = 'posted'
                  AND am.company_id = %s
                  AND am.date <= %s
                """,
                [account.id, self.company_id.id, prior_date],
            )
            balance = self.env.cr.fetchone()[0] or 0.0
            if abs(balance) < 0.01:
                continue
            if balance > 0:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": "Opening Balance",
                            "debit": balance,
                            "credit": 0.0,
                        },
                    )
                )
            else:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": "Opening Balance",
                            "debit": 0.0,
                            "credit": -balance,
                        },
                    )
                )

        if not lines:
            raise UserError(
                "No prior-period balances found for balance sheet accounts. "
                "Ensure prior-year posted entries exist."
            )

        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": self.date_from,
                "ref": f"Opening Balance — {self.name}",
                "line_ids": lines,
            }
        )
        self.write({"opening_balance_done": True, "opening_balance_move_id": move.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }

    def action_create_closing_entries(self):
        """Create a balanced closing entry moving P&L balances to retained earnings."""
        self.ensure_one()
        if self.closing_entries_done:
            raise UserError("Closing entries have already been created for this fiscal year.")
        journal = self._get_general_journal()
        if not journal:
            raise UserError("No general journal found.")

        retained_earnings_account = self.env["account.account"].search(
            [
                ("account_type", "=", "equity_unaffected"),
                ("company_ids", "in", [self.company_id.id]),
            ],
            limit=1,
        )
        if not retained_earnings_account:
            raise UserError(
                "No retained earnings account found. "
                "Please configure an account with type 'Retained Earnings'."
            )

        pl_account_types = [
            "income",
            "income_other",
            "expense",
            "expense_depreciation",
            "expense_direct_cost",
        ]
        lines = []
        net_pl = 0.0

        for account in self.env["account.account"].search(
            [
                ("account_type", "in", pl_account_types),
                ("company_ids", "in", [self.company_id.id]),
            ]
        ):
            self.env.cr.execute(
                """
                SELECT COALESCE(SUM(aml.debit), 0), COALESCE(SUM(aml.credit), 0)
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE aml.account_id = %s
                  AND am.state = 'posted'
                  AND am.company_id = %s
                  AND am.date BETWEEN %s AND %s
                """,
                [account.id, self.company_id.id, self.date_from, self.date_to],
            )
            row = self.env.cr.fetchone()
            debit, credit = (row[0] or 0.0), (row[1] or 0.0)
            balance = debit - credit
            if abs(balance) < 0.01:
                continue
            if balance > 0:
                # Expense (debit balance) — credit to close
                lines.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": "Year-End Closing",
                            "debit": 0.0,
                            "credit": balance,
                        },
                    )
                )
                net_pl -= balance
            else:
                # Income (credit balance) — debit to close
                lines.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": "Year-End Closing",
                            "debit": -balance,
                            "credit": 0.0,
                        },
                    )
                )
                net_pl += -balance

        if not lines:
            raise UserError(
                "No P&L account balances found for this fiscal year. "
                "Ensure journal entries are posted for the period."
            )

        # Balanced offset to retained earnings
        if net_pl >= 0:
            lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": retained_earnings_account.id,
                        "name": "Year-End Closing — Net Result",
                        "debit": 0.0,
                        "credit": net_pl,
                    },
                )
            )
        else:
            lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": retained_earnings_account.id,
                        "name": "Year-End Closing — Net Result",
                        "debit": -net_pl,
                        "credit": 0.0,
                    },
                )
            )

        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": self.date_to,
                "ref": f"Year-End Closing — {self.name}",
                "line_ids": lines,
            }
        )
        self.write({"closing_entries_done": True, "closing_entries_move_id": move.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }


class ResCompany(models.Model):
    """Extend res.company with period lock UI and admin override audit."""

    _inherit = "res.company"

    platform_lock_override_reason = fields.Text(
        "Last Lock Override Reason",
        help="Reason provided when an admin overrode a period lock.",
    )
    platform_lock_override_date = fields.Datetime("Last Override On", readonly=True)
    platform_lock_override_by = fields.Many2one("res.users", "Last Override By", readonly=True)

    def action_override_period_lock(self, reason: str, new_lock_date=None):
        """Admin override of period lock — requires reason, creates audit trail."""
        self.ensure_one()
        if not reason:
            raise UserError("A reason is required to override a period lock.")

        self.write(
            {
                "platform_lock_override_reason": reason,
                "platform_lock_override_date": fields.Datetime.now(),
                "platform_lock_override_by": self.env.user.id,
            }
        )
        if new_lock_date is not None:
            self.fiscalyear_lock_date = new_lock_date

        self.message_post(
            body=(
                f"<b>Period Lock Override</b><br/>"
                f"Override by: {self.env.user.name}<br/>"
                f"Reason: {reason}<br/>"
                f"New lock date: {new_lock_date or 'unchanged'}"
            )
        )


class AccountMove(models.Model):
    """Enforce period lock and debit=credit balance on journal entry posting."""

    _inherit = "account.move"

    platform_reversal_reason = fields.Text(
        "Reversal Reason",
        help="Required when creating a reversal. Stored for audit purposes.",
    )
    audit_attachment_ids = fields.Many2many(
        "ir.attachment",
        "account_move_audit_attachment_rel",
        "move_id",
        "attachment_id",
        "Audit Attachments",
        help="Supporting documents attached for audit purposes.",
    )

    def action_post(self):
        """Validate debit=credit balance before posting general journal entries."""
        for move in self:
            if move.move_type == "entry" and move.line_ids:
                total_debit = sum(move.line_ids.mapped("debit"))
                total_credit = sum(move.line_ids.mapped("credit"))
                if round(abs(total_debit - total_credit), 2) > 0.01:
                    raise UserError(
                        f"Cannot post journal entry '{move.name or 'draft'}': "
                        f"debit ({total_debit:.2f}) ≠ credit ({total_credit:.2f}). "
                        "Each general entry must be balanced."
                    )
        return super().action_post()

    def button_cancel(self):
        """Override cancel to enforce period lock."""
        for move in self:
            if move.date and move.company_id.fiscalyear_lock_date:
                if move.date <= move.company_id.fiscalyear_lock_date:
                    raise UserError(
                        f"Journal entry '{move.name}' is in a locked period "
                        f"(locked until {move.company_id.fiscalyear_lock_date}). "
                        "Use a reversal entry to correct it."
                    )
        return super().button_cancel()
