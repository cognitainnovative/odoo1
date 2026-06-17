"""Payroll run — a period's payroll batch."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayrollRun(models.Model):
    _name = "hr.payroll.run"
    _description = "Payroll Run"
    _inherit = ["mail.thread"]
    _order = "period_start desc"
    _rec_name = "name"

    name = fields.Char("Reference", required=True, default="New")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    period_type = fields.Selection(
        [("monthly", "Monthly"), ("4week", "4-Weekly")],
        default="monthly",
        required=True,
    )
    period_start = fields.Date("Period Start", required=True)
    period_end = fields.Date("Period End", required=True)
    rule_version_id = fields.Many2one(
        "hr.payroll.rule.version",
        "Rule Version",
        default=lambda s: s.env["hr.payroll.rule.version"].get_active_rules(),
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("calculated", "Calculated"),
            ("confirmed", "Confirmed"),
            ("approved", "Approved"),
            ("posted", "Posted to Journal"),
            ("exported", "Exported"),
        ],
        default="draft",
        tracking=True,
    )
    payslip_ids = fields.One2many("hr.payroll.payslip", "payroll_run_id", "Payslips")
    payslip_count = fields.Integer(compute="_compute_payslip_count")
    journal_id = fields.Many2one(
        "account.journal",
        "Payroll Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    journal_move_id = fields.Many2one("account.move", "Journal Entry", readonly=True)

    # Summary totals
    total_gross = fields.Float(compute="_compute_totals", digits=(14, 2), store=True)
    total_net = fields.Float(compute="_compute_totals", digits=(14, 2), store=True)
    total_loonheffing = fields.Float(compute="_compute_totals", digits=(14, 2), store=True)
    total_employer_cost = fields.Float(compute="_compute_totals", digits=(14, 2), store=True)

    @api.depends("payslip_ids")
    def _compute_payslip_count(self):
        for run in self:
            run.payslip_count = len(run.payslip_ids)

    @api.depends(
        "payslip_ids.gross_salary",
        "payslip_ids.net_salary",
        "payslip_ids.loonheffing",
        "payslip_ids.total_employer_cost",
    )
    def _compute_totals(self):
        for run in self:
            run.total_gross = sum(run.payslip_ids.mapped("gross_salary"))
            run.total_net = sum(run.payslip_ids.mapped("net_salary"))
            run.total_loonheffing = sum(run.payslip_ids.mapped("loonheffing"))
            run.total_employer_cost = sum(run.payslip_ids.mapped("total_employer_cost"))

    def action_calculate(self):
        """Calculate payslips for all active employees."""
        self.ensure_one()
        if not self.rule_version_id:
            raise UserError("Please select a rule version before calculating.")

        employees = self.env["hr.employee"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("payroll_gross_monthly", ">", 0),
                ("active", "=", True),
            ]
        )
        if not employees:
            raise UserError(
                "No employees with payroll data found for this company. "
                "Set a gross monthly salary on at least one active employee "
                "before running payroll."
            )

        # Remove old draft payslips
        self.payslip_ids.filtered(lambda p: p.state == "draft").unlink()

        for employee in employees:
            slip = self.env["hr.payroll.payslip"].create(
                {
                    "employee_id": employee.id,
                    "payroll_run_id": self.id,
                    "period_start": self.period_start,
                    "period_end": self.period_end,
                    "rule_version_id": self.rule_version_id.id,
                }
            )
            slip.action_calculate()

        self.state = "calculated"
        return True

    def action_confirm(self):
        for slip in self.payslip_ids:
            if slip.state == "calculated":
                slip.state = "confirmed"
        self.state = "confirmed"

    def action_approve(self):
        for slip in self.payslip_ids:
            if slip.state == "confirmed":
                slip.state = "approved"
        self.state = "approved"

    def action_post_journal(self):
        """Create journal entries for the payroll run."""
        self.ensure_one()
        if not self.journal_id:
            raise UserError("Please select a payroll journal before posting.")

        # Build journal lines
        lines = []
        for slip in self.payslip_ids.filtered(lambda s: s.state == "approved"):
            # Debit: Gross wage expense account (placeholder)
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": f"Gross wages {slip.employee_id.name} {slip.period_start}",
                        "debit": slip.gross_salary + slip.employer_costs_total,
                        "credit": 0,
                        "account_id": self._get_wage_account().id,
                    },
                )
            )
            # Credit: Net salary payable
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": f"Net salary {slip.employee_id.name}",
                        "debit": 0,
                        "credit": slip.net_salary,
                        "account_id": self._get_salary_payable_account().id,
                    },
                )
            )
            # Credit: Loonheffing payable
            if slip.loonheffing:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "name": f"Loonheffing {slip.employee_id.name}",
                            "debit": 0,
                            "credit": slip.loonheffing,
                            "account_id": self._get_tax_payable_account().id,
                        },
                    )
                )

        if not lines:
            raise UserError("No approved payslips to post.")

        move = self.env["account.move"].create(
            {
                "journal_id": self.journal_id.id,
                "date": self.period_end,
                "ref": f"Payroll {self.name}",
                "line_ids": lines,
            }
        )
        self.journal_move_id = move
        self.state = "posted"
        for slip in self.payslip_ids.filtered(lambda s: s.state == "approved"):
            slip.journal_move_id = move

    def _get_wage_account(self):
        return self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )

    def _get_salary_payable_account(self):
        return self.env["account.account"].search(
            [("account_type", "=", "liability_payable"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )

    def _get_tax_payable_account(self):
        return self.env["account.account"].search(
            [("account_type", "=", "liability_payable"), ("company_id", "=", self.company_id.id)],
            order="id desc",
            limit=1,
        )

    def _log_export_access(self):
        """Write an 'export' access log entry for every payslip in this run."""
        for slip in self.payslip_ids:
            try:
                self.env["hr.payroll.access.log"].sudo().with_context(skip_access_log=True).create(
                    {
                        "payslip_id": slip.id,
                        "user_id": self.env.user.id,
                        "access_type": "export",
                    }
                )
            except Exception:
                pass  # Never block exports due to audit log failure

    def action_export_accountant(self):
        """Export payroll data as CSV for accountant."""
        import base64
        import csv
        import io

        self._log_export_access()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Employee",
                "Period",
                "Gross",
                "Loonheffing",
                "Pension Employee",
                "Net",
                "Employer Cost",
                "Vakantiegeld Accrual",
            ]
        )
        for slip in self.payslip_ids:
            writer.writerow(
                [
                    slip.employee_id.name,
                    str(slip.period_start),
                    slip.gross_salary,
                    slip.loonheffing,
                    slip.pension_employee,
                    slip.net_salary,
                    slip.total_employer_cost,
                    slip.vakantiegeld_accrual,
                ]
            )

        csv_content = output.getvalue().encode("utf-8")
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"Payroll_{self.name}_accountant.csv",
                "type": "binary",
                "datas": base64.b64encode(csv_content),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_export_payroll_provider(self):
        """Export payroll run data in a structured format for payroll provider hand-off.

        NOTE: This generates a prepared export file.
        It does NOT constitute an official loonaangifte (wage tax filing).
        Direct filing to the Belastingdienst requires a certified submission route.
        """
        import base64
        import csv
        import io

        self._log_export_access()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(
            [
                "loonheffingsnummer",
                "period_start",
                "period_end",
                "period_type",
                "employee_name",
                "bsn_last4",
                "gross_salary",
                "overtime_gross",
                "bonus_gross",
                "sick_pay_gross",
                "allowances",
                "expense_reimbursement",
                "vakantiegeld_accrual",
                "vakantiegeld_pct",
                "loonheffing",
                "loonheffingskorting_applied",
                "lhk_amount",
                "pension_employee",
                "pension_employer",
                "awf_employer",
                "zvw_employer",
                "total_employer_cost",
                "net_salary",
            ]
        )
        lhfnr = self.company_id.loonheffingsnummer or ""
        for slip in self.payslip_ids:
            emp = slip.employee_id
            writer.writerow(
                [
                    lhfnr,
                    str(slip.period_start),
                    str(slip.period_end),
                    slip.period_type,
                    emp.name,
                    emp.bsn_last4 or "",
                    slip.gross_salary,
                    slip.overtime_gross,
                    slip.bonus_gross,
                    slip.sick_pay_gross,
                    slip.allowances,
                    slip.expense_reimbursement,
                    slip.vakantiegeld_accrual,
                    slip.vakantiegeld_pct,
                    slip.loonheffing,
                    slip.loonheffingskorting_applied,
                    slip.loonheffingskorting_amount,
                    slip.pension_employee,
                    slip.pension_employer,
                    slip.awf_employer,
                    slip.zvw_employer,
                    slip.total_employer_cost,
                    slip.net_salary,
                ]
            )

        csv_content = output.getvalue().encode("utf-8")
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"Payroll_{self.name}_provider_export.csv",
                "type": "binary",
                "datas": base64.b64encode(csv_content),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_export_annual_statement(self):
        """Export annual statement (jaaropgaaf) data for all employees in this run's year.

        Generates a CSV with YTD gross, loonheffing, net, and vakantiegeld per employee
        for the fiscal year of this run's period. Data is sourced from YTD accumulators
        on hr.employee — ensure all payroll runs for the year are calculated first.

        This is prepared data for employee annual statements.
        It is NOT an official Belastingdienst submission.
        """
        import base64
        import csv
        import io

        year = self.period_start.year if self.period_start else fields.Date.today().year
        self._log_export_access()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Fiscal Year",
                "Employee Name",
                "BSN (last 4)",
                "YTD Gross (€)",
                "YTD Loonheffing (€)",
                "YTD Vakantiegeld Accrued (€)",
                "YTD Net (€)",
                "Note",
            ]
        )
        note = (
            "PREPARED DATA — Not an official Belastingdienst submission. "
            "Use a certified payroll provider for official loonaangifte."
        )
        for emp in self.env["hr.employee"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("ytd_year", "=", year),
                ("ytd_gross", ">", 0),
            ]
        ):
            writer.writerow(
                [
                    year,
                    emp.name,
                    emp.bsn_last4 or "",
                    emp.ytd_gross,
                    emp.ytd_loonheffing,
                    emp.ytd_vakantiegeld,
                    emp.ytd_net,
                    note,
                ]
            )

        csv_content = output.getvalue().encode("utf-8")
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"Annual_Statement_{year}.csv",
                "type": "binary",
                "datas": base64.b64encode(csv_content),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_publish_payslips(self):
        """Publish approved payslips to employee portal."""
        for slip in self.payslip_ids.filtered(lambda s: s.state == "approved"):
            slip.action_publish()
        self.state = "exported"
