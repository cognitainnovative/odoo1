"""Simplified budget vs actual model."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountBudget(models.Model):
    _name = "account.budget.platform"
    _description = "Budget"
    _inherit = ["mail.thread"]
    _order = "date_from desc, name"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    date_from = fields.Date("From", required=True)
    date_to = fields.Date("To", required=True)

    @api.constrains("date_from", "date_to")
    def _check_date_from_date_to_order(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError("Budget end date must be after the start date.")

    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("done", "Done")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("account.budget.line.platform", "budget_id", "Budget Lines")
    total_budget = fields.Float(compute="_compute_totals", store=True, digits=(14, 2))
    total_actual = fields.Float(compute="_compute_totals", store=True, digits=(14, 2))
    variance = fields.Float(compute="_compute_totals", store=True, digits=(14, 2))
    variance_pct = fields.Float(compute="_compute_totals", store=True, digits=(6, 2))

    @api.depends("line_ids.budgeted_amount", "line_ids.actual_amount")
    def _compute_totals(self):
        for budget in self:
            total_b = sum(budget.line_ids.mapped("budgeted_amount"))
            total_a = sum(budget.line_ids.mapped("actual_amount"))
            budget.total_budget = total_b
            budget.total_actual = total_a
            budget.variance = total_a - total_b
            budget.variance_pct = ((total_a - total_b) / total_b * 100) if total_b else 0.0

    def action_activate(self):
        self.write({"state": "active"})

    def action_compute_actuals(self):
        """Refresh actual amounts from posted journal entries."""
        for budget in self:
            for line in budget.line_ids:
                line._compute_actual()


class AccountBudgetLine(models.Model):
    _name = "account.budget.line.platform"
    _description = "Budget Line"
    _order = "sequence"

    budget_id = fields.Many2one("account.budget.platform", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    account_id = fields.Many2one("account.account", "Account")
    budgeted_amount = fields.Float("Budget (€)", digits=(14, 2))
    actual_amount = fields.Float("Actual (€)", digits=(14, 2), readonly=True)
    variance = fields.Float("Variance (€)", compute="_compute_variance", store=True, digits=(14, 2))

    @api.depends("budgeted_amount", "actual_amount")
    def _compute_variance(self):
        for line in self:
            line.variance = line.actual_amount - line.budgeted_amount

    def _compute_actual(self):
        """Pull actual amount from posted journal entries for this account + period."""
        for line in self:
            if not line.account_id or not line.budget_id:
                continue
            budget = line.budget_id
            self.env.cr.execute(
                """
                SELECT COALESCE(SUM(aml.debit - aml.credit), 0)
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE am.state = 'posted'
                  AND am.company_id = %s
                  AND am.date BETWEEN %s AND %s
                  AND aml.account_id = %s
                """,
                [
                    budget.company_id.id,
                    budget.date_from,
                    budget.date_to,
                    line.account_id.id,
                ],
            )
            line.actual_amount = self.env.cr.fetchone()[0] or 0.0
