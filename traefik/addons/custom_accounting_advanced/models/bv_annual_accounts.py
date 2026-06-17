"""Dutch BV Annual Accounts preparation model."""

import base64
import csv
import io
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BvAnnualAccounts(models.Model):
    _name = "bv.annual.accounts"
    _description = "BV Annual Accounts Package"
    _inherit = ["mail.thread"]
    _order = "fiscal_year desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    fiscal_year = fields.Integer("Fiscal Year", required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Accountant Review"),
            ("approved", "Approved"),
            ("filed", "Filed"),
        ],
        default="draft",
        tracking=True,
    )

    # Balance sheet data
    total_assets = fields.Float("Total Assets (€)", digits=(14, 2))
    total_liabilities = fields.Float("Total Liabilities (€)", digits=(14, 2))
    total_equity = fields.Float("Total Equity (€)", digits=(14, 2))

    # P&L data
    total_revenue = fields.Float("Total Revenue (€)", digits=(14, 2))
    total_expenses = fields.Float("Total Expenses (€)", digits=(14, 2))
    net_result = fields.Float("Net Result (€)", compute="_compute_net_result", store=True)

    # Retained earnings
    retained_earnings_start = fields.Float("Retained Earnings (Start of Year)", digits=(14, 2))
    dividends = fields.Float("Dividends (€)", digits=(14, 2), default=0.0)
    retained_earnings_end = fields.Float(
        "Retained Earnings (End of Year)", compute="_compute_retained_earnings", store=True
    )

    # Notes & management report
    notes = fields.Html("Notes to Financial Statements")
    management_report = fields.Html("Management Report / Director's Commentary")
    auditor_notes = fields.Text("Auditor / Accountant Notes")

    # Accountant access
    accountant_id = fields.Many2one("res.users", "Assigned Accountant")
    accountant_review_date = fields.Datetime("Review Submitted", readonly=True)
    accountant_approved_date = fields.Datetime("Approved By Accountant", readonly=True)

    # Documents
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "bv_annual_accounts_attachment_rel",
        "annual_accounts_id",
        "attachment_id",
        "Documents",
    )

    @api.depends("total_revenue", "total_expenses")
    def _compute_net_result(self):
        for rec in self:
            rec.net_result = rec.total_revenue - rec.total_expenses

    @api.depends("retained_earnings_start", "net_result", "dividends")
    def _compute_retained_earnings(self):
        for rec in self:
            rec.retained_earnings_end = rec.retained_earnings_start + rec.net_result - rec.dividends

    def action_submit_for_review(self):
        self.ensure_one()
        if not self.accountant_id:
            raise UserError("Please assign an accountant before submitting for review.")
        self.write({"state": "review", "accountant_review_date": fields.Datetime.now()})
        if self.accountant_id.partner_id:
            self.message_post(
                body=f"Annual accounts for {self.fiscal_year} submitted for your review.",
                partner_ids=[self.accountant_id.partner_id.id],
            )

    def action_approve(self):
        self.write({"state": "approved", "accountant_approved_date": fields.Datetime.now()})

    def action_file(self):
        """Mark as filed — this is an administrative flag, NOT actual filing."""
        self.write({"state": "filed"})
        self.message_post(
            body=(
                "⚠️  Marked as filed. Note: actual filing with the KvK (Kamer van Koophandel) "
                "must be done via the official publication pathway."
            )
        )

    def action_pull_from_accounting(self):
        """Pull current year totals from Odoo's account.move records."""
        self.ensure_one()
        from datetime import date

        year_start = date(self.fiscal_year, 1, 1)
        year_end = date(self.fiscal_year, 12, 31)

        # Revenue: sum of credit on income accounts
        self.env.cr.execute(
            """
            SELECT COALESCE(SUM(aml.credit - aml.debit), 0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.state = 'posted'
              AND am.company_id = %s
              AND am.date BETWEEN %s AND %s
              AND aa.account_type = 'income'
            """,
            [self.company_id.id, year_start, year_end],
        )
        revenue = self.env.cr.fetchone()[0] or 0.0

        # Expenses
        self.env.cr.execute(
            """
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.state = 'posted'
              AND am.company_id = %s
              AND am.date BETWEEN %s AND %s
              AND aa.account_type = 'expense'
            """,
            [self.company_id.id, year_start, year_end],
        )
        expenses = self.env.cr.fetchone()[0] or 0.0

        self.write({"total_revenue": revenue, "total_expenses": expenses})

    def action_export_csv(self):
        """Export annual accounts summary as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Amount (€)"])
        writer.writerows(
            [
                ["Fiscal Year", self.fiscal_year],
                ["Total Revenue", self.total_revenue],
                ["Total Expenses", self.total_expenses],
                ["Net Result", self.net_result],
                ["Total Assets", self.total_assets],
                ["Total Liabilities", self.total_liabilities],
                ["Total Equity", self.total_equity],
                ["Retained Earnings (end)", self.retained_earnings_end],
            ]
        )
        csv_bytes = output.getvalue().encode("utf-8")
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"Annual_Accounts_{self.company_id.name}_{self.fiscal_year}.csv",
                "type": "binary",
                "datas": base64.b64encode(csv_bytes),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
