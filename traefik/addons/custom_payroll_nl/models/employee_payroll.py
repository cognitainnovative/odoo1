"""Employee payroll profile — extends hr.employee with payroll-specific data."""

from odoo import fields, models


class HrEmployeePayroll(models.Model):
    _inherit = "hr.employee"

    # ── Payroll profile ───────────────────────────────────────────────────────
    payroll_gross_monthly = fields.Float("Gross Monthly Salary (€)", digits=(12, 2))
    payroll_hourly_wage = fields.Float("Hourly Wage (€)", digits=(8, 4))
    payroll_contract_hours = fields.Float("Contract Hours/Week", default=40.0)
    payroll_loonheffingskorting = fields.Boolean(
        "Apply Loonheffingskorting",
        default=True,
        help="Apply wage tax credit (loonheffingskorting). "
        "Typically True for primary employer, False for secondary jobs.",
    )
    payroll_pension_employee_pct = fields.Float("Pension Employee (%)", default=4.0, digits=(5, 2))
    payroll_pension_employer_pct = fields.Float("Pension Employer (%)", default=8.0, digits=(5, 2))
    payroll_vakantiegeld_pct = fields.Float(
        "Holiday Allowance (%)", default=8.0, digits=(5, 2), help="Minimum 8% per Dutch law."
    )
    payroll_travel_km = fields.Float("Commute Distance (km one way)")
    payroll_travel_days = fields.Integer("Travel Days / Month", default=20)
    payroll_other_allowances = fields.Float("Other Allowances (€/month)", digits=(12, 2))
    payroll_has_company_car = fields.Boolean("Company Car")
    payroll_company_car_ev = fields.Boolean("EV / Electric Car")
    payroll_company_car_catalogue_value = fields.Float(
        "Car Catalogue Value (€)",
        digits=(12, 2),
        help="Catalogusprijs for bijtelling calculation. "
        "Bijtelling = catalogue × rate / 12 and is added to taxable gross.",
    )

    # ── Tax data ──────────────────────────────────────────────────────────────
    bsn_last4 = fields.Char(
        "BSN (last 4 digits only)",
        size=4,
        help="Store ONLY the last 4 digits for identification. Never store the full BSN.",
    )
    sofi_number_provided = fields.Boolean("Sofinummer / BSN Provided to HR")

    # ── YTD tracking ──────────────────────────────────────────────────────────
    ytd_gross = fields.Float("YTD Gross (€)", readonly=True, digits=(12, 2))
    ytd_net = fields.Float("YTD Net (€)", readonly=True, digits=(12, 2))
    ytd_loonheffing = fields.Float("YTD Loonheffing (€)", readonly=True, digits=(12, 2))
    ytd_vakantiegeld = fields.Float("YTD Vakantiegeld Accrued (€)", readonly=True, digits=(12, 2))
    ytd_year = fields.Integer("YTD Year", readonly=True)

    def reset_ytd(self, year: int):
        """Reset YTD counters for a new year."""
        self.write(
            {
                "ytd_gross": 0.0,
                "ytd_net": 0.0,
                "ytd_loonheffing": 0.0,
                "ytd_vakantiegeld": 0.0,
                "ytd_year": year,
            }
        )
