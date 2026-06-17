"""Dutch payroll calculation engine.

All tax parameters are passed in as arguments from versioned rule records.
No hardcoded tables — everything is configurable per year.

References (2025):
  - Loonheffingstarieven 2025 (simplified two-bracket model)
  - Loonheffingskorting (arbeidskorting + algemene heffingskorting)
  - Werkgeverslasten: AWF (WW), ZVW (Zorgverzekeringswet)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PayrollResult:
    """Complete payroll calculation result with full explanation."""

    # Gross components
    gross_salary: float = 0.0
    overtime_gross: float = 0.0
    bonus_gross: float = 0.0
    allowances: float = 0.0  # travel, meal, other
    expense_reimbursement: float = 0.0  # net reimbursements (not taxed)

    # Holiday allowance (vakantiegeld)
    vakantiegeld_accrual: float = 0.0  # accrued this period
    vakantiegeld_pct: float = 8.0

    # Gross before tax
    taxable_gross: float = 0.0

    # Deductions (employee-side)
    loonheffing: float = (
        0.0  # wage tax (includes loonbelasting + social premiums via wage tax table)
    )
    pension_employee: float = 0.0
    other_deductions: float = 0.0

    # Net salary
    net_salary: float = 0.0

    # Employer contributions (not deducted from employee pay)
    pension_employer: float = 0.0
    awf_employer: float = 0.0  # WW (Algemeen Werkloosheidsfonds)
    zvw_employer: float = 0.0  # Health insurance employer part
    total_employer_cost: float = 0.0

    # Year-to-date totals (passed in, updated by caller)
    ytd_gross: float = 0.0
    ytd_net: float = 0.0

    # Company car bijtelling
    bijtelling: float = 0.0

    # Applied credits
    loonheffingskorting_applied: bool = False
    loonheffingskorting_amount: float = 0.0

    # Explanation lines for payslip display + audit
    explanation: list[dict] = field(default_factory=list)

    def add_explanation(self, code: str, name: str, amount: float, note: str = ""):
        self.explanation.append(
            {"code": code, "name": name, "amount": round(amount, 2), "note": note}
        )


def calculate_loonheffing(
    taxable_gross: float,
    bracket1_rate: float,
    bracket1_max: float,
    bracket2_rate: float,
    apply_lhk: bool,
    lhk_amount: float,
    lhk_afbouw_start: float,
    lhk_afbouw_end: float,
    lhk_afbouw_rate: float,
    period_type: str = "monthly",
) -> tuple[float, float, str]:
    """Calculate Dutch wage tax (loonheffing) for one period.

    Returns: (loonheffing_amount, lhk_applied, explanation_note)

    Args:
        taxable_gross: Gross salary this period (before loonheffing)
        bracket1_rate: Tax rate for income up to bracket1_max (e.g. 0.3697 for 36.97%)
        bracket1_max: Upper limit of bracket 1 (annual; converted to period internally)
        bracket2_rate: Tax rate above bracket1_max (e.g. 0.4950)
        apply_lhk: Whether to apply loonheffingskorting (wage tax credit)
        lhk_amount: Maximum loonheffingskorting per year
        lhk_afbouw_start: Annual income where lhk starts phasing out
        lhk_afbouw_end: Annual income where lhk is fully phased out
        lhk_afbouw_rate: Phaseout rate (per € above afbouw_start)
        period_type: "monthly" | "4week"
    """
    periods = 12 if period_type == "monthly" else 13

    # Annualise for bracket calculation
    annual_gross = taxable_gross * periods

    # Calculate annual tax using two-bracket model
    if annual_gross <= bracket1_max:
        annual_tax = annual_gross * bracket1_rate
    else:
        annual_tax = (bracket1_max * bracket1_rate) + (
            (annual_gross - bracket1_max) * bracket2_rate
        )

    # Apply loonheffingskorting
    lhk_applied = 0.0
    lhk_note = ""
    if apply_lhk:
        # Compute effective LHK with afbouw (phaseout)
        if annual_gross <= lhk_afbouw_start:
            lhk_applied = lhk_amount
        elif annual_gross >= lhk_afbouw_end:
            lhk_applied = 0.0
        else:
            afbouw = (annual_gross - lhk_afbouw_start) * lhk_afbouw_rate
            lhk_applied = max(0.0, lhk_amount - afbouw)
        annual_tax = max(0.0, annual_tax - lhk_applied)
        lhk_note = f"LHK applied: €{lhk_applied/periods:.2f}/period (annual €{lhk_applied:.2f})"

    # De-annualise back to period
    period_tax = annual_tax / periods
    return round(period_tax, 2), round(lhk_applied / periods, 2), lhk_note


def calculate_payslip(
    gross_monthly: float,
    *,
    overtime_gross: float = 0.0,
    bonus_gross: float = 0.0,
    travel_allowance: float = 0.0,
    other_allowances: float = 0.0,
    expense_reimbursement: float = 0.0,
    pension_employee_pct: float = 4.0,
    pension_employer_pct: float = 8.0,
    vakantiegeld_pct: float = 8.0,
    loonheffingskorting: bool = True,
    period_type: str = "monthly",
    # Rule version parameters
    bracket1_rate: float = 0.3697,
    bracket1_max: float = 38_098.0,
    bracket2_rate: float = 0.4950,
    lhk_amount: float = 3_362.0,
    lhk_afbouw_start: float = 10_000.0,
    lhk_afbouw_end: float = 124_936.0,
    lhk_afbouw_rate: float = 0.0206 / 12,
    awf_employer_pct: float = 2.74,
    zvw_employer_pct: float = 6.57,
    # Company car bijtelling
    has_company_car: bool = False,
    company_car_ev: bool = False,
    bijtelling_ev_pct: float = 16.0,
    bijtelling_standard_pct: float = 22.0,
    company_car_catalogue_value: float = 0.0,
) -> PayrollResult:
    """Calculate a full Dutch payroll period for one employee.

    All percentages are absolute (e.g. 4.0 for 4%, not 0.04).
    Returns a PayrollResult with full explanation for audit.
    """
    periods = 12 if period_type == "monthly" else 13

    result = PayrollResult(
        vakantiegeld_pct=vakantiegeld_pct,
        loonheffingskorting_applied=loonheffingskorting,
    )

    # ── 1. Gross components ────────────────────────────────────────────────────
    result.gross_salary = round(gross_monthly, 2)
    result.overtime_gross = round(overtime_gross, 2)
    result.bonus_gross = round(bonus_gross, 2)
    result.allowances = round(travel_allowance + other_allowances, 2)
    result.expense_reimbursement = round(expense_reimbursement, 2)

    result.add_explanation("GROSS", "Gross Salary", result.gross_salary)
    if overtime_gross:
        result.add_explanation("OT", "Overtime", result.overtime_gross)
    if bonus_gross:
        result.add_explanation("BONUS", "Bonus", result.bonus_gross)
    if result.allowances:
        result.add_explanation("ALLOW", "Allowances (travel + other)", result.allowances)

    # ── 1b. Bijtelling — company car taxable benefit ───────────────────────────
    if has_company_car and company_car_catalogue_value > 0:
        rate = bijtelling_ev_pct if company_car_ev else bijtelling_standard_pct
        result.bijtelling = round(company_car_catalogue_value * (rate / 100) / periods, 2)
        result.add_explanation(
            "BIJTELLING",
            f"Bijtelling Company Car ({'EV' if company_car_ev else 'Standard'} {rate}%)",
            result.bijtelling,
            f"€{company_car_catalogue_value:,.0f} × {rate}% / {periods} periods",
        )

    # ── 2. Taxable gross (allowances + bijtelling included; expense reimbursements excluded) ─
    result.taxable_gross = round(
        result.gross_salary
        + result.overtime_gross
        + result.bonus_gross
        + result.allowances
        + result.bijtelling,
        2,
    )

    # ── 3. Vakantiegeld (holiday allowance) accrual ────────────────────────────
    result.vakantiegeld_accrual = round(result.gross_salary * (vakantiegeld_pct / 100), 2)
    result.add_explanation(
        "VG",
        f"Holiday Allowance ({vakantiegeld_pct}% of gross)",
        result.vakantiegeld_accrual,
        "Accrued — not paid this period",
    )

    # ── 4. Pension (employee) ──────────────────────────────────────────────────
    result.pension_employee = round(result.taxable_gross * (pension_employee_pct / 100), 2)
    if result.pension_employee:
        result.add_explanation(
            "PENSIOEN_E", f"Pension Employee ({pension_employee_pct}%)", -result.pension_employee
        )

    # Pension is deducted before loonheffing calculation (pre-tax)
    pension_deductible = result.pension_employee

    # ── 5. Loonheffing ─────────────────────────────────────────────────────────
    lhk_afbouw_rate_per_period = lhk_afbouw_rate
    loonheffing, lhk_period, lhk_note = calculate_loonheffing(
        taxable_gross=result.taxable_gross - pension_deductible,
        bracket1_rate=bracket1_rate,
        bracket1_max=bracket1_max,
        bracket2_rate=bracket2_rate,
        apply_lhk=loonheffingskorting,
        lhk_amount=lhk_amount,
        lhk_afbouw_start=lhk_afbouw_start,
        lhk_afbouw_end=lhk_afbouw_end,
        lhk_afbouw_rate=lhk_afbouw_rate_per_period,
        period_type=period_type,
    )
    result.loonheffing = loonheffing
    result.loonheffingskorting_amount = lhk_period
    result.add_explanation("LH", "Loonheffing (wage tax)", -result.loonheffing, lhk_note)

    # ── 6. Net salary ──────────────────────────────────────────────────────────
    # IMPORTANT: bijtelling (company-car benefit) is included in taxable_gross so
    # it is TAXED, but the employee never receives it as cash — they receive the
    # car's private use instead. It must be subtracted back out of the net, or
    # the employee would be paid the bijtelling amount in cash (a real bug).
    result.net_salary = round(
        result.taxable_gross
        - result.bijtelling  # taxed but not paid in cash
        - result.pension_employee
        - result.loonheffing
        + result.expense_reimbursement,
        2,
    )
    result.add_explanation("NET", "Net Salary", result.net_salary)

    # ── 7. Employer costs ──────────────────────────────────────────────────────
    result.pension_employer = round(result.taxable_gross * (pension_employer_pct / 100), 2)
    result.awf_employer = round(result.taxable_gross * (awf_employer_pct / 100), 2)
    result.zvw_employer = round(result.taxable_gross * (zvw_employer_pct / 100), 2)
    result.total_employer_cost = round(
        result.taxable_gross + result.pension_employer + result.awf_employer + result.zvw_employer,
        2,
    )

    result.add_explanation(
        "PENSIOEN_W",
        f"Pension Employer ({pension_employer_pct}%)",
        result.pension_employer,
        "Employer cost — not deducted from employee pay",
    )
    result.add_explanation("AWF", f"AWF/WW Employer ({awf_employer_pct}%)", result.awf_employer)
    result.add_explanation("ZVW", f"ZVW Employer ({zvw_employer_pct}%)", result.zvw_employer)
    result.add_explanation("TOTAL_COST", "Total Employer Cost", result.total_employer_cost)

    return result
