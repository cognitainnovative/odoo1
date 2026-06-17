"""Brutal edge-case tests for custom_payroll_nl (M10).

Payroll = real money, so these pin down the gross->net math the standard tests
don't fully assert:
  - bijtelling must NOT inflate cash net (the bug: company car was paid as cash)
  - net is always < gross for normal salaries; never negative
  - higher gross -> higher tax (monotonic); LHK reduces tax
  - vakantiegeld accrual exact; expense reimbursement untaxed but added to net
  - employer cost > gross; 4-week vs monthly period consistency
  - zero / tiny gross handled
"""

from odoo.addons.custom_payroll_nl.lib.nl_payroll_calculator import calculate_payslip
from odoo.tests.common import TransactionCase


class TestBrutalGrossToNet(TransactionCase):

    P = {"loonheffingskorting": True, "period_type": "monthly"}

    def test_bijtelling_does_not_inflate_cash_net(self):
        """THE BUG: a company car is a taxable benefit, not cash. Net WITH a car
        must be LOWER than without (more tax, no extra cash) — never higher."""
        no_car = calculate_payslip(3000.0, **self.P)
        with_car = calculate_payslip(
            3000.0, has_company_car=True, company_car_catalogue_value=40000.0, **self.P
        )
        self.assertLess(
            with_car.net_salary,
            no_car.net_salary,
            "Net with a company car must be LOWER (taxable benefit, not cash). "
            "If higher, bijtelling is being wrongly paid out as cash net.",
        )
        # And the tax must be higher (the benefit IS taxed)
        self.assertGreater(with_car.loonheffing, no_car.loonheffing)

    def test_net_less_than_gross(self):
        r = calculate_payslip(3500.0, **self.P)
        self.assertLess(r.net_salary, r.gross_salary)
        self.assertGreater(r.net_salary, 0)

    def test_higher_gross_higher_tax(self):
        low = calculate_payslip(2000.0, **self.P)
        high = calculate_payslip(6000.0, **self.P)
        self.assertGreater(high.loonheffing, low.loonheffing)

    def test_lhk_increases_net(self):
        with_lhk = calculate_payslip(3000.0, loonheffingskorting=True, period_type="monthly")
        without = calculate_payslip(3000.0, loonheffingskorting=False, period_type="monthly")
        self.assertGreater(with_lhk.net_salary, without.net_salary)

    def test_expense_reimbursement_untaxed_added_to_net(self):
        base = calculate_payslip(3000.0, **self.P)
        with_exp = calculate_payslip(3000.0, expense_reimbursement=200.0, **self.P)
        # tax unchanged, net up by exactly the reimbursement
        self.assertAlmostEqual(with_exp.loonheffing, base.loonheffing, places=2)
        self.assertAlmostEqual(with_exp.net_salary, base.net_salary + 200.0, places=2)

    def test_vakantiegeld_exact(self):
        r = calculate_payslip(4000.0, vakantiegeld_pct=8.0, **self.P)
        self.assertAlmostEqual(r.vakantiegeld_accrual, 320.0, places=2)

    def test_employer_cost_exceeds_gross(self):
        r = calculate_payslip(3000.0, **self.P)
        self.assertGreater(r.total_employer_cost, r.gross_salary)

    def test_zero_gross_no_crash(self):
        r = calculate_payslip(0.0, **self.P)
        self.assertEqual(r.gross_salary, 0.0)
        self.assertEqual(r.loonheffing, 0.0)
        self.assertGreaterEqual(r.net_salary, 0.0)

    def test_net_never_negative_low_income(self):
        r = calculate_payslip(500.0, **self.P)
        self.assertGreaterEqual(r.net_salary, 0.0)

    def test_ev_car_less_tax_than_standard(self):
        ev = calculate_payslip(
            3000.0,
            has_company_car=True,
            company_car_ev=True,
            company_car_catalogue_value=40000.0,
            **self.P,
        )
        std = calculate_payslip(
            3000.0,
            has_company_car=True,
            company_car_ev=False,
            company_car_catalogue_value=40000.0,
            **self.P,
        )
        # EV has lower bijtelling -> lower taxable -> lower tax -> higher net
        self.assertLess(ev.loonheffing, std.loonheffing)
        self.assertGreater(ev.net_salary, std.net_salary)


class TestBrutalPeriodConsistency(TransactionCase):
    """4-week (13 periods) vs monthly (12) should both be sane and self-consistent."""

    def test_4week_uses_13_periods(self):
        monthly = calculate_payslip(3000.0, loonheffingskorting=True, period_type="monthly")
        fourweek = calculate_payslip(3000.0, loonheffingskorting=True, period_type="4week")
        # both produce positive net < gross; 4-week annualises over 13
        self.assertGreater(fourweek.net_salary, 0)
        self.assertLess(fourweek.net_salary, fourweek.gross_salary)
        # different period basis -> different tax (not identical)
        self.assertNotAlmostEqual(monthly.loonheffing, fourweek.loonheffing, places=2)


class TestBrutalTaxBracket(TransactionCase):
    """Two-bracket model: income above bracket1_max taxed at higher rate."""

    def test_high_earner_hits_second_bracket(self):
        # 10000/month = 120k/year, above the 38098 bracket1 -> effective rate
        # should exceed bracket1_rate
        r = calculate_payslip(10000.0, loonheffingskorting=False, period_type="monthly")
        effective = r.loonheffing / r.taxable_gross
        self.assertGreater(
            effective, 0.3697, "High earner's effective rate should exceed bracket-1 rate."
        )
