"""Payslip — individual employee payslip for one period."""

import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayrollPayslip(models.Model):
    _name = "hr.payroll.payslip"
    _description = "Payslip"
    _inherit = ["mail.thread"]
    _order = "period_start desc, employee_id"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    payroll_run_id = fields.Many2one("hr.payroll.run", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="payroll_run_id.company_id", store=True)
    rule_version_id = fields.Many2one("hr.payroll.rule.version", required=True)

    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    period_type = fields.Selection(related="payroll_run_id.period_type", store=True)

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("calculated", "Calculated"),
            ("confirmed", "Confirmed"),
            ("approved", "Approved"),
            ("published", "Published to Portal"),
        ],
        default="draft",
        tracking=True,
    )

    # ── Gross components ──────────────────────────────────────────────────────
    gross_salary = fields.Float("Gross Salary (€)", digits=(12, 2))
    overtime_gross = fields.Float("Overtime (€)", digits=(12, 2))
    bonus_gross = fields.Float("Bonus (€)", digits=(12, 2))
    allowances = fields.Float("Allowances (€)", digits=(12, 2))
    expense_reimbursement = fields.Float("Expense Reimbursement (€)", digits=(12, 2))
    sick_pay_gross = fields.Float(
        "Sick Pay (€)",
        digits=(12, 2),
        default=0.0,
        help="Placeholder for sick-pay supplement. "
        "Actual amount depends on collective labour agreement (CLA) and sick-leave status. "
        "Enter manually or integrate with custom_hrm sick-leave records.",
    )

    # ── Holiday allowance ─────────────────────────────────────────────────────
    vakantiegeld_accrual = fields.Float("Vakantiegeld Accrual (€)", digits=(12, 2))
    vakantiegeld_pct = fields.Float("Vakantiegeld %", digits=(5, 2))

    # ── Deductions ────────────────────────────────────────────────────────────
    loonheffing = fields.Float("Loonheffing (€)", digits=(12, 2))
    pension_employee = fields.Float("Pension Employee (€)", digits=(12, 2))
    loonheffingskorting_applied = fields.Boolean("LHK Applied")
    loonheffingskorting_amount = fields.Float("LHK Amount (€)", digits=(12, 2))

    # ── Net ───────────────────────────────────────────────────────────────────
    net_salary = fields.Float("Net Salary (€)", digits=(12, 2))

    # ── Employer contributions ────────────────────────────────────────────────
    pension_employer = fields.Float("Pension Employer (€)", digits=(12, 2))
    awf_employer = fields.Float("AWF/WW Employer (€)", digits=(12, 2))
    zvw_employer = fields.Float("ZVW Employer (€)", digits=(12, 2))
    total_employer_cost = fields.Float("Total Employer Cost (€)", digits=(12, 2))

    employer_costs_total = fields.Float(compute="_compute_employer_costs_total", digits=(12, 2))

    # ── Explanation / audit ───────────────────────────────────────────────────
    calculation_json = fields.Text("Calculation Detail (JSON)", readonly=True)
    calculation_warning = fields.Text("Calculation Warnings", readonly=True)

    # ── Override log ──────────────────────────────────────────────────────────
    override_ids = fields.One2many("hr.payroll.override", "payslip_id", "Manual Overrides")

    # ── Journal ───────────────────────────────────────────────────────────────
    journal_move_id = fields.Many2one("account.move", "Journal Entry", readonly=True)

    @api.depends("employee_id", "period_start")
    def _compute_name(self):
        for slip in self:
            emp = slip.employee_id.name or "?"
            period = str(slip.period_start)[:7] if slip.period_start else "?"
            slip.name = f"Payslip {emp} {period}"

    @api.depends("pension_employer", "awf_employer", "zvw_employer")
    def _compute_employer_costs_total(self):
        for slip in self:
            slip.employer_costs_total = (
                slip.pension_employer + slip.awf_employer + slip.zvw_employer
            )

    def action_calculate(self):
        """Run the Dutch payroll calculation for this payslip."""
        self.ensure_one()
        from ..lib.nl_payroll_calculator import calculate_payslip

        emp = self.employee_id
        rv = self.rule_version_id

        if not rv:
            raise UserError("No rule version selected for this payslip.")
        if not emp.payroll_gross_monthly:
            _logger.warning("Employee %s has no gross monthly salary configured.", emp.name)
            self.calculation_warning = "No gross monthly salary configured."
            return

        warnings = []
        if not rv.is_active:
            warnings.append(f"Rule version {rv.display_name} is not marked as current.")
        if rv.year and self.period_start and rv.year != self.period_start.year:
            warnings.append(
                f"Rule version year ({rv.year}) does not match payslip period year "
                f"({self.period_start.year}). Verify tax parameters are correct for this fiscal year."
            )

        # Travel allowance calculation
        max_km = rv.max_km_vergoeding
        travel_allowance = (
            emp.payroll_travel_km * 2 * emp.payroll_travel_days * max_km
            if emp.payroll_travel_km
            else 0
        )

        result = calculate_payslip(
            gross_monthly=emp.payroll_gross_monthly,
            overtime_gross=self.overtime_gross,
            bonus_gross=self.bonus_gross,
            travel_allowance=travel_allowance,
            other_allowances=emp.payroll_other_allowances,
            expense_reimbursement=self.expense_reimbursement,
            pension_employee_pct=emp.payroll_pension_employee_pct,
            pension_employer_pct=emp.payroll_pension_employer_pct,
            vakantiegeld_pct=emp.payroll_vakantiegeld_pct,
            loonheffingskorting=emp.payroll_loonheffingskorting,
            period_type=self.period_type or "monthly",
            bracket1_rate=rv.bracket1_rate / 100,
            bracket1_max=rv.bracket1_max,
            bracket2_rate=rv.bracket2_rate / 100,
            lhk_amount=rv.lhk_max_amount,
            lhk_afbouw_start=rv.lhk_afbouw_start,
            lhk_afbouw_end=rv.lhk_afbouw_end,
            lhk_afbouw_rate=rv.lhk_afbouw_rate / 100,
            awf_employer_pct=rv.awf_employer_pct,
            zvw_employer_pct=rv.zvw_employer_pct,
            has_company_car=emp.payroll_has_company_car,
            company_car_ev=emp.payroll_company_car_ev,
            bijtelling_ev_pct=rv.bijtelling_ev_pct,
            bijtelling_standard_pct=rv.bijtelling_standard_pct,
            company_car_catalogue_value=emp.payroll_company_car_catalogue_value,
        )

        self.write(
            {
                "gross_salary": result.gross_salary,
                "overtime_gross": result.overtime_gross,
                "bonus_gross": result.bonus_gross,
                "allowances": result.allowances,
                "expense_reimbursement": result.expense_reimbursement,
                "vakantiegeld_accrual": result.vakantiegeld_accrual,
                "vakantiegeld_pct": result.vakantiegeld_pct,
                "loonheffing": result.loonheffing,
                "pension_employee": result.pension_employee,
                "loonheffingskorting_applied": result.loonheffingskorting_applied,
                "loonheffingskorting_amount": result.loonheffingskorting_amount,
                "net_salary": result.net_salary,
                "pension_employer": result.pension_employer,
                "awf_employer": result.awf_employer,
                "zvw_employer": result.zvw_employer,
                "total_employer_cost": result.total_employer_cost,
                "calculation_json": json.dumps(result.explanation, ensure_ascii=False),
                "calculation_warning": "\n".join(warnings) if warnings else False,
                "state": "calculated",
            }
        )

        # Update YTD
        year = self.period_start.year if self.period_start else fields.Date.today().year
        if emp.ytd_year != year:
            emp.reset_ytd(year)
        emp.ytd_gross += result.gross_salary
        emp.ytd_net += result.net_salary
        emp.ytd_loonheffing += result.loonheffing
        emp.ytd_vakantiegeld += result.vakantiegeld_accrual

    def action_publish(self):
        """Publish this payslip to the employee portal."""
        for slip in self:
            if slip.state not in ("approved",):
                continue
            slip.state = "published"
            if slip.employee_id.user_id:
                slip.message_post(
                    body="Your payslip is available in the employee portal.",
                    partner_ids=[slip.employee_id.user_id.partner_id.id],
                )

    def action_apply_override(self, field_name: str, new_value: float, reason: str):
        """Manually override a payslip field with audit trail."""
        self.ensure_one()
        if not reason:
            raise UserError("A reason is required for manual overrides.")

        original = getattr(self, field_name, 0.0)
        self.env["hr.payroll.override"].create(
            {
                "payslip_id": self.id,
                "field_name": field_name,
                "original_value": original,
                "override_value": new_value,
                "reason": reason,
                "override_by_id": self.env.user.id,
            }
        )
        self.write({field_name: new_value})
        self.env["platform.audit.log"].log(
            "payroll_override",
            res_model=self._name,
            res_id=self.id,
            res_name=self.name,
            summary=(
                f"Payroll override on '{field_name}' for {self.employee_id.name}: "
                f"{original} → {new_value}"
            ),
            details={"field": field_name, "original": original, "new": new_value, "reason": reason},
            severity="critical",
        )


class HrPayrollOverride(models.Model):
    _name = "hr.payroll.override"
    _description = "Payslip Manual Override"
    _order = "create_date desc"

    payslip_id = fields.Many2one("hr.payroll.payslip", required=True, ondelete="cascade")
    field_name = fields.Char("Field", required=True)
    original_value = fields.Float("Original Value", digits=(12, 2))
    override_value = fields.Float("Override Value", digits=(12, 2))
    reason = fields.Text("Reason", required=True)
    override_by_id = fields.Many2one(
        "res.users", "Override By", readonly=True, default=lambda s: s.env.user
    )
    override_date = fields.Datetime("Override Date", default=fields.Datetime.now, readonly=True)

    def write(self, vals):
        raise UserError("Payroll override records cannot be modified.")


class HrPayrollAccessLog(models.Model):
    """Immutable audit log: every read of a payslip record is recorded here."""

    _name = "hr.payroll.access.log"
    _description = "Payroll Access Audit Log"
    _order = "access_date desc"
    _rec_name = "payslip_id"

    payslip_id = fields.Many2one(
        "hr.payroll.payslip", ondelete="cascade", index=True, required=True
    )
    user_id = fields.Many2one(
        "res.users", "Accessed By", readonly=True, default=lambda s: s.env.user
    )
    access_date = fields.Datetime("Accessed At", readonly=True, default=fields.Datetime.now)
    access_type = fields.Selection(
        [("read", "Read"), ("export", "Export")], default="read", readonly=True
    )

    def write(self, vals):
        raise UserError("Payroll access log records cannot be modified.")

    def unlink(self):
        raise UserError("Payroll access log records cannot be deleted.")


class HrPayrollPayslipAudited(models.Model):
    """Extend hr.payroll.payslip to write access log entries on read."""

    _inherit = "hr.payroll.payslip"

    def read(self, fields=None, load="_classic_read"):
        result = super().read(fields=fields, load=load)
        if self.ids and not self.env.context.get("skip_access_log"):
            try:
                for rec_id in self.ids:
                    self.env["hr.payroll.access.log"].sudo().with_context(
                        skip_access_log=True
                    ).create(
                        {
                            "payslip_id": rec_id,
                            "user_id": self.env.user.id,
                            "access_type": "read",
                        }
                    )
            except Exception:
                pass  # Never block payslip reads due to audit log failure
        return result
