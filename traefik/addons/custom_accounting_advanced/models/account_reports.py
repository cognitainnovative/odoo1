"""Accounting reports: trial balance, general ledger, aged balance, VAT summary, cash flow, cost centres."""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


# ── Cost Centre ────────────────────────────────────────────────────────────────


class AccountCostCentre(models.Model):
    _name = "account.cost.centre"
    _description = "Cost Centre"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "code, name"

    name = fields.Char(required=True)
    code = fields.Char("Code", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    active = fields.Boolean(default=True)
    description = fields.Text()
    parent_id = fields.Many2one(
        "account.cost.centre", "Parent Centre", ondelete="set null", index=True
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("account.cost.centre", "parent_id", "Sub-Centres")

    _cost_centre_code_uniq = models.Constraint(
        "UNIQUE(company_id, code)",
        "Cost centre code must be unique per company.",
    )


class AccountMoveLineCostCentreExt(models.Model):
    _inherit = "account.move.line"

    cost_centre_id = fields.Many2one(
        "account.cost.centre",
        "Cost Centre",
        index=True,
        help="Assign this journal line to a cost centre for management reporting.",
    )


# ── Trial Balance ──────────────────────────────────────────────────────────────


class AccountTrialBalanceLine(models.TransientModel):
    _name = "account.trial.balance.line"
    _description = "Trial Balance Result Line"
    _order = "account_code"

    wizard_id = fields.Many2one("account.trial.balance.wizard", ondelete="cascade")
    account_code = fields.Char("Account Code")
    account_name = fields.Char("Account Name")
    account_type = fields.Char("Account Type")
    debit_total = fields.Float("Total Debit", digits=(14, 2))
    credit_total = fields.Float("Total Credit", digits=(14, 2))
    balance = fields.Float("Balance", digits=(14, 2))


class AccountTrialBalanceWizard(models.TransientModel):
    _name = "account.trial.balance.wizard"
    _description = "Trial Balance Wizard"

    date_from = fields.Date("From Date", required=True)
    date_to = fields.Date("To Date", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    line_ids = fields.One2many("account.trial.balance.line", "wizard_id", "Lines")

    def action_generate(self):
        self.ensure_one()
        self.line_ids.unlink()
        domain = [
            ("move_id.state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("move_id.date", ">=", self.date_from),
            ("move_id.date", "<=", self.date_to),
        ]
        groups = self.env["account.move.line"].read_group(
            domain, ["account_id", "debit:sum", "credit:sum"], ["account_id"]
        )
        lines = []
        for g in groups:
            account = self.env["account.account"].browse(g["account_id"][0])
            debit = g.get("debit", 0.0) or 0.0
            credit = g.get("credit", 0.0) or 0.0
            lines.append(
                {
                    "wizard_id": self.id,
                    "account_code": account.code or "",
                    "account_name": account.name or "",
                    "account_type": account.account_type or "",
                    "debit_total": debit,
                    "credit_total": credit,
                    "balance": debit - credit,
                }
            )
        lines.sort(key=lambda line: line["account_code"])
        if lines:
            self.env["account.trial.balance.line"].create(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.trial.balance.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


# ── General Ledger ─────────────────────────────────────────────────────────────


class AccountGeneralLedgerLine(models.TransientModel):
    _name = "account.general.ledger.line"
    _description = "General Ledger Result Line"
    _order = "account_code, entry_date, entry_ref"

    wizard_id = fields.Many2one("account.general.ledger.wizard", ondelete="cascade")
    entry_date = fields.Date("Date")
    entry_ref = fields.Char("Entry Ref")
    account_code = fields.Char("Account Code")
    account_name = fields.Char("Account Name")
    partner_name = fields.Char("Partner")
    description = fields.Char("Description")
    debit = fields.Float("Debit", digits=(14, 2))
    credit = fields.Float("Credit", digits=(14, 2))


class AccountGeneralLedgerWizard(models.TransientModel):
    _name = "account.general.ledger.wizard"
    _description = "General Ledger Wizard"

    date_from = fields.Date("From Date", required=True)
    date_to = fields.Date("To Date", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    account_id = fields.Many2one("account.account", "Account (optional)")
    line_ids = fields.One2many("account.general.ledger.line", "wizard_id", "Lines")

    def action_generate(self):
        self.ensure_one()
        self.line_ids.unlink()
        domain = [
            ("move_id.state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("move_id.date", ">=", self.date_from),
            ("move_id.date", "<=", self.date_to),
        ]
        if self.account_id:
            domain.append(("account_id", "=", self.account_id.id))
        move_lines = self.env["account.move.line"].search(
            domain, order="account_id asc, date asc, move_id asc"
        )
        lines = [
            {
                "wizard_id": self.id,
                "entry_date": aml.move_id.date,
                "entry_ref": aml.move_id.name or "",
                "account_code": aml.account_id.code or "",
                "account_name": aml.account_id.name or "",
                "partner_name": aml.partner_id.name or "",
                "description": aml.name or "",
                "debit": aml.debit,
                "credit": aml.credit,
            }
            for aml in move_lines
        ]
        if lines:
            self.env["account.general.ledger.line"].create(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.general.ledger.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


# ── Aged Balance ───────────────────────────────────────────────────────────────


class AccountAgedBalanceLine(models.TransientModel):
    _name = "account.aged.balance.line"
    _description = "Aged Balance Result Line"
    _order = "partner_name"

    wizard_id = fields.Many2one("account.aged.balance.wizard", ondelete="cascade")
    partner_name = fields.Char("Partner")
    current = fields.Float("Current (not overdue)", digits=(14, 2))
    days_30 = fields.Float("1–30 days", digits=(14, 2))
    days_60 = fields.Float("31–60 days", digits=(14, 2))
    days_90 = fields.Float("61–90 days", digits=(14, 2))
    overdue_90plus = fields.Float("90+ days", digits=(14, 2))
    total = fields.Float("Total", digits=(14, 2))


class AccountAgedBalanceWizard(models.TransientModel):
    _name = "account.aged.balance.wizard"
    _description = "Aged Balance Wizard"

    date_at = fields.Date("As of Date", required=True, default=fields.Date.today)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    aged_type = fields.Selection(
        [("receivable", "Receivables"), ("payable", "Payables")],
        default="receivable",
        required=True,
    )
    line_ids = fields.One2many("account.aged.balance.line", "wizard_id", "Lines")

    def action_generate(self):
        self.ensure_one()
        self.line_ids.unlink()
        account_type = "asset_receivable" if self.aged_type == "receivable" else "liability_payable"
        self.env.cr.execute(
            """
            SELECT
                COALESCE(rp.name, 'Unknown') AS partner_name,
                am.invoice_date_due,
                COALESCE(SUM(aml.balance), 0) AS balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            WHERE aa.account_type = %s
              AND am.state = 'posted'
              AND am.company_id = %s
              AND aml.reconciled = FALSE
              AND am.date <= %s
            GROUP BY rp.name, am.invoice_date_due
            """,
            [account_type, self.company_id.id, self.date_at],
        )
        partner_buckets = {}
        for partner_name, due_date, balance in self.env.cr.fetchall():
            if partner_name not in partner_buckets:
                partner_buckets[partner_name] = [0.0, 0.0, 0.0, 0.0, 0.0]
            if due_date is None or due_date >= self.date_at:
                bucket = 0
            else:
                days_overdue = (self.date_at - due_date).days
                if days_overdue <= 30:
                    bucket = 1
                elif days_overdue <= 60:
                    bucket = 2
                elif days_overdue <= 90:
                    bucket = 3
                else:
                    bucket = 4
            partner_buckets[partner_name][bucket] += balance

        lines = []
        for pname, buckets in sorted(partner_buckets.items()):
            total = sum(buckets)
            if abs(total) < 0.01:
                continue
            lines.append(
                {
                    "wizard_id": self.id,
                    "partner_name": pname,
                    "current": buckets[0],
                    "days_30": buckets[1],
                    "days_60": buckets[2],
                    "days_90": buckets[3],
                    "overdue_90plus": buckets[4],
                    "total": total,
                }
            )
        if lines:
            self.env["account.aged.balance.line"].create(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.aged.balance.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


# ── VAT Summary ────────────────────────────────────────────────────────────────


class AccountVatSummaryLine(models.TransientModel):
    _name = "account.vat.summary.line"
    _description = "VAT Summary Result Line"
    _order = "tax_name"

    wizard_id = fields.Many2one("account.vat.summary.wizard", ondelete="cascade")
    tax_name = fields.Char("Tax")
    base_amount = fields.Float("Taxable Base (€)", digits=(14, 2))
    tax_amount = fields.Float("Tax Amount (€)", digits=(14, 2))


class AccountVatSummaryWizard(models.TransientModel):
    _name = "account.vat.summary.wizard"
    _description = "VAT Summary Wizard"

    date_from = fields.Date("From Date", required=True)
    date_to = fields.Date("To Date", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    line_ids = fields.One2many("account.vat.summary.line", "wizard_id", "Lines")

    def action_generate(self):
        self.ensure_one()
        self.line_ids.unlink()
        tax_lines = self.env["account.move.line"].search(
            [
                ("move_id.state", "=", "posted"),
                ("move_id.company_id", "=", self.company_id.id),
                ("move_id.date", ">=", self.date_from),
                ("move_id.date", "<=", self.date_to),
                ("tax_line_id", "!=", False),
            ]
        )
        tax_totals = {}
        for line in tax_lines:
            tax_name = line.tax_line_id.name or "Unknown Tax"
            if tax_name not in tax_totals:
                tax_totals[tax_name] = {"base": 0.0, "tax": 0.0}
            tax_totals[tax_name]["tax"] += line.balance
            tax_totals[tax_name]["base"] += line.tax_base_amount

        lines = [
            {
                "wizard_id": self.id,
                "tax_name": tax_name,
                "base_amount": totals["base"],
                "tax_amount": totals["tax"],
            }
            for tax_name, totals in sorted(tax_totals.items())
        ]
        if lines:
            self.env["account.vat.summary.line"].create(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.vat.summary.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


# ── Cash Flow ──────────────────────────────────────────────────────────────────


class AccountCashFlowWizard(models.TransientModel):
    _name = "account.cash.flow.wizard"
    _description = "Cash Flow Statement Wizard (simplified indirect method)"

    date_from = fields.Date("From Date", required=True)
    date_to = fields.Date("To Date", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    operating_total = fields.Float("Operating Activities (€)", digits=(14, 2), readonly=True)
    investing_total = fields.Float("Investing Activities (€)", digits=(14, 2), readonly=True)
    financing_total = fields.Float("Financing Activities (€)", digits=(14, 2), readonly=True)
    net_cash_flow = fields.Float("Net Cash Flow (€)", digits=(14, 2), readonly=True)

    def action_generate(self):
        self.ensure_one()

        def _sum_types(types):
            if not types:
                return 0.0
            placeholders = ", ".join(["%s"] * len(types))
            self.env.cr.execute(
                f"""
                SELECT COALESCE(SUM(aml.credit - aml.debit), 0)
                FROM account_move_line aml
                JOIN account_account aa ON aa.id = aml.account_id
                JOIN account_move am ON am.id = aml.move_id
                WHERE am.state = 'posted'
                  AND am.company_id = %s
                  AND am.date BETWEEN %s AND %s
                  AND aa.account_type IN ({placeholders})
                """,
                [self.company_id.id, self.date_from, self.date_to] + list(types),
            )
            return self.env.cr.fetchone()[0] or 0.0

        # Indirect method approximation
        net_income = _sum_types(
            [
                "income",
                "income_other",
                "expense",
                "expense_depreciation",
                "expense_direct_cost",
            ]
        )
        working_capital = _sum_types(
            [
                "asset_receivable",
                "liability_payable",
                "asset_current",
                "liability_current",
                "asset_prepayments",
            ]
        )
        operating = net_income + working_capital
        investing = _sum_types(["asset_fixed", "asset_non_current"])
        financing = _sum_types(["equity", "equity_unaffected", "liability_non_current"])

        self.write(
            {
                "operating_total": operating,
                "investing_total": investing,
                "financing_total": financing,
                "net_cash_flow": operating + investing + financing,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.cash.flow.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
