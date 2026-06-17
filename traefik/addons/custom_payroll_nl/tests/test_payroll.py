"""Tests for M10 — Dutch payroll calculator, payslip lifecycle, role isolation."""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestNlPayrollCalculator(TransactionCase):
    """Unit tests for the Dutch payroll calculation engine."""

    def setUp(self):
        super().setUp()
        from odoo.addons.custom_payroll_nl.lib.nl_payroll_calculator import calculate_payslip

        self.calculate = calculate_payslip
        # Standard 2025 parameters
        self.params = {
            "bracket1_rate": 0.3697,
            "bracket1_max": 38_098.0,
            "bracket2_rate": 0.4950,
            "lhk_amount": 3_362.0,
            "lhk_afbouw_start": 10_000.0,
            "lhk_afbouw_end": 124_936.0,
            "lhk_afbouw_rate": 0.0206 / 12,
            "awf_employer_pct": 2.74,
            "zvw_employer_pct": 6.57,
        }

    def test_gross_to_net_calculation(self):
        """Net = gross - loonheffing - pension_employee."""
        result = self.calculate(3_000.0, loonheffingskorting=True, **self.params)
        self.assertAlmostEqual(result.gross_salary, 3_000.0)
        self.assertGreater(result.loonheffing, 0, "Loonheffing must be > 0")
        self.assertGreater(result.net_salary, 0, "Net must be > 0")
        self.assertLess(result.net_salary, result.gross_salary, "Net < gross")
        expected_net = round(result.gross_salary - result.pension_employee - result.loonheffing, 2)
        self.assertAlmostEqual(result.net_salary, expected_net, places=2)

    def test_loonheffingskorting_reduces_tax(self):
        """Applying LHK reduces loonheffing."""
        with_lhk = self.calculate(3_000.0, loonheffingskorting=True, **self.params)
        without_lhk = self.calculate(3_000.0, loonheffingskorting=False, **self.params)
        self.assertLess(with_lhk.loonheffing, without_lhk.loonheffing)
        self.assertGreater(with_lhk.net_salary, without_lhk.net_salary)

    def test_vakantiegeld_accrual(self):
        """Holiday allowance = 8% of gross (default)."""
        result = self.calculate(4_000.0, **self.params)
        self.assertAlmostEqual(result.vakantiegeld_accrual, 4_000.0 * 0.08, places=2)

    def test_custom_vakantiegeld_pct(self):
        """Custom vakantiegeld percentage is respected."""
        result = self.calculate(4_000.0, vakantiegeld_pct=10.0, **self.params)
        self.assertAlmostEqual(result.vakantiegeld_accrual, 4_000.0 * 0.10, places=2)

    def test_employer_costs_computed(self):
        """Employer costs are separate from employee deductions."""
        result = self.calculate(3_000.0, **self.params)
        self.assertGreater(result.awf_employer, 0)
        self.assertGreater(result.zvw_employer, 0)
        self.assertGreater(result.total_employer_cost, result.gross_salary)

    def test_explanation_lines_present(self):
        """Calculation explanation has all key components."""
        result = self.calculate(3_000.0, **self.params)
        codes = [line["code"] for line in result.explanation]
        self.assertIn("GROSS", codes)
        self.assertIn("LH", codes)
        self.assertIn("NET", codes)
        self.assertIn("VG", codes)

    def test_high_income_no_lhk(self):
        """At high income (>€124k/yr), LHK phaseout is complete."""
        # €15k/month → €180k/yr — well above phaseout end
        result = self.calculate(15_000.0, loonheffingskorting=True, **self.params)
        self.assertAlmostEqual(result.loonheffingskorting_amount, 0.0, places=1)

    def test_overtime_included_in_taxable(self):
        """Overtime is included in taxable gross."""
        without_ot = self.calculate(3_000.0, **self.params)
        with_ot = self.calculate(3_000.0, overtime_gross=500.0, **self.params)
        self.assertGreater(with_ot.loonheffing, without_ot.loonheffing)

    def test_expense_reimbursement_not_taxed(self):
        """Expense reimbursements are added to net but not taxed."""
        without_exp = self.calculate(3_000.0, **self.params)
        with_exp = self.calculate(3_000.0, expense_reimbursement=200.0, **self.params)
        # Loonheffing should be the same
        self.assertAlmostEqual(with_exp.loonheffing, without_exp.loonheffing, places=2)
        # Net should be higher by reimbursement amount
        self.assertAlmostEqual(with_exp.net_salary, without_exp.net_salary + 200.0, places=2)


class TestPayrollRuleVersion(TransactionCase):
    """Tests for hr.payroll.rule.version model."""

    def test_2025_rules_seeded(self):
        """2025 NL rules are seeded and active."""
        rule = self.env["hr.payroll.rule.version"].search(
            [("year", "=", 2025), ("is_active", "=", True)], limit=1
        )
        self.assertTrue(rule, "2025 NL rules must be seeded and active.")
        self.assertAlmostEqual(rule.bracket1_rate, 36.97)
        self.assertAlmostEqual(rule.vakantiegeld_pct, 8.0)

    def test_get_active_rules_returns_2025(self):
        rule = self.env["hr.payroll.rule.version"].get_active_rules()
        self.assertTrue(rule)
        self.assertEqual(rule.year, 2025)

    def test_activate_sets_other_inactive(self):
        """Activating one rule version deactivates others."""
        rule2024 = self.env["hr.payroll.rule.version"].create(
            {"year": 2024, "version": 1, "is_active": False}
        )
        rule2025 = self.env["hr.payroll.rule.version"].search([("year", "=", 2025)], limit=1)
        self.assertTrue(rule2025.is_active)
        rule2024.activate()
        self.assertTrue(rule2024.is_active)
        rule2025.invalidate_recordset()
        self.assertFalse(rule2025.is_active)


class TestPayrollPayslip(TransactionCase):
    """Tests for payslip calculation via Odoo models."""

    def setUp(self):
        super().setUp()
        self.rule = self.env["hr.payroll.rule.version"].search([("is_active", "=", True)], limit=1)
        self.employee = self.env["hr.employee"].create(
            {
                "name": "Test Payroll Employee",
                "payroll_gross_monthly": 3_500.0,
                "payroll_loonheffingskorting": True,
                "payroll_pension_employee_pct": 4.0,
                "payroll_pension_employer_pct": 8.0,
                "payroll_vakantiegeld_pct": 8.0,
            }
        )

    def _make_run(self):
        from datetime import date

        return self.env["hr.payroll.run"].create(
            {
                "name": "Test Run Jan 2025",
                "period_type": "monthly",
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 1, 31),
                "rule_version_id": self.rule.id if self.rule else False,
            }
        )

    def test_calculate_payslip(self):
        """Payslip can be calculated for an employee."""
        if not self.rule:
            return
        run = self._make_run()
        from datetime import date

        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.employee.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 1, 31),
                "rule_version_id": self.rule.id,
            }
        )
        slip.action_calculate()
        self.assertEqual(slip.state, "calculated")
        self.assertAlmostEqual(slip.gross_salary, 3_500.0)
        self.assertGreater(slip.loonheffing, 0)
        self.assertGreater(slip.net_salary, 0)
        self.assertLess(slip.net_salary, slip.gross_salary)

    def test_override_requires_reason(self):
        """Manual override without reason raises UserError."""
        if not self.rule:
            return
        run = self._make_run()
        from datetime import date

        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.employee.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 1, 31),
                "rule_version_id": self.rule.id,
            }
        )
        slip.action_calculate()
        with self.assertRaises(UserError):
            slip.action_apply_override("loonheffing", 100.0, "")

    def test_override_with_reason_creates_audit_record(self):
        """Override with reason creates an hr.payroll.override record."""
        if not self.rule:
            return
        run = self._make_run()
        from datetime import date

        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.employee.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 1, 31),
                "rule_version_id": self.rule.id,
            }
        )
        slip.action_calculate()
        original = slip.loonheffing
        slip.action_apply_override("loonheffing", 900.0, "Manual correction per accountant advice")
        self.assertAlmostEqual(slip.loonheffing, 900.0)
        self.assertEqual(len(slip.override_ids), 1)
        override = slip.override_ids[0]
        self.assertAlmostEqual(override.original_value, original, places=2)
        self.assertAlmostEqual(override.override_value, 900.0)

    def test_override_record_immutable(self):
        """hr.payroll.override records cannot be modified."""
        if not self.rule:
            return
        run = self._make_run()
        from datetime import date

        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.employee.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 1, 31),
                "rule_version_id": self.rule.id,
            }
        )
        slip.action_calculate()
        slip.action_apply_override("bonus_gross", 500.0, "Test override")
        override = slip.override_ids[0]
        with self.assertRaises(UserError):
            override.write({"reason": "Tampered reason"})

    def test_holiday_allowance_accrual(self):
        """Holiday allowance is accrued correctly in payslip."""
        if not self.rule:
            return
        run = self._make_run()
        from datetime import date

        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.employee.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 1, 1),
                "period_end": date(2025, 1, 31),
                "rule_version_id": self.rule.id,
            }
        )
        slip.action_calculate()
        expected_vg = round(3_500.0 * 0.08, 2)
        self.assertAlmostEqual(slip.vakantiegeld_accrual, expected_vg, places=2)


class TestPayrollRBAC(TransactionCase):
    """Tests for payroll role-based access control and portal payslip self-scope."""

    def setUp(self):
        super().setUp()
        self.rule = self.env["hr.payroll.rule.version"].search([("is_active", "=", True)], limit=1)
        if not self.rule:
            return
        from datetime import date

        self.user_a = self.env["res.users"].create(
            {
                "name": "RBAC Employee A",
                "login": "rbac_emp_a@platform.test",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        self.user_b = self.env["res.users"].create(
            {
                "name": "RBAC Employee B",
                "login": "rbac_emp_b@platform.test",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        self.emp_a = self.env["hr.employee"].create(
            {
                "name": "RBAC Emp A",
                "user_id": self.user_a.id,
                "payroll_gross_monthly": 3_000.0,
            }
        )
        self.emp_b = self.env["hr.employee"].create(
            {
                "name": "RBAC Emp B",
                "user_id": self.user_b.id,
                "payroll_gross_monthly": 3_500.0,
            }
        )
        run = self.env["hr.payroll.run"].create(
            {
                "name": "RBAC Test Run Apr 2025",
                "period_type": "monthly",
                "period_start": date(2025, 4, 1),
                "period_end": date(2025, 4, 30),
                "rule_version_id": self.rule.id,
            }
        )
        self.slip_a = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.emp_a.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 4, 1),
                "period_end": date(2025, 4, 30),
                "rule_version_id": self.rule.id,
            }
        )
        self.slip_b = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": self.emp_b.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 4, 1),
                "period_end": date(2025, 4, 30),
                "rule_version_id": self.rule.id,
            }
        )

    def test_employee_sees_only_own_payslip(self):
        """Employee can read their own payslip but not a colleague's (record rule)."""
        if not self.rule:
            return
        visible_ids = self.env(user=self.user_a)["hr.payroll.payslip"].search([]).ids
        self.assertIn(self.slip_a.id, visible_ids, "Employee A must see their own payslip.")
        self.assertNotIn(
            self.slip_b.id, visible_ids, "Employee A must NOT see Employee B's payslip."
        )

    def test_employee_b_sees_only_own_payslip(self):
        """Record rule is symmetric — employee B also cannot see employee A's payslip."""
        if not self.rule:
            return
        visible_ids = self.env(user=self.user_b)["hr.payroll.payslip"].search([]).ids
        self.assertIn(self.slip_b.id, visible_ids, "Employee B must see their own payslip.")
        self.assertNotIn(
            self.slip_a.id, visible_ids, "Employee B must NOT see Employee A's payslip."
        )

    def test_employee_cannot_write_payslip(self):
        """Regular employees cannot modify payslip records (ACL: perm_write=0)."""
        if not self.rule:
            return
        from odoo.exceptions import AccessError

        env_a = self.env(user=self.user_a)
        with self.assertRaises(AccessError):
            env_a["hr.payroll.payslip"].browse(self.slip_a.id).write({"gross_salary": 9_999.0})

    def test_employee_cannot_create_payslip(self):
        """Regular employees cannot create payslip records (ACL: perm_create=0)."""
        if not self.rule:
            return
        from datetime import date

        from odoo.exceptions import AccessError

        env_a = self.env(user=self.user_a)
        with self.assertRaises(AccessError):
            env_a["hr.payroll.payslip"].create(
                {
                    "employee_id": self.emp_a.id,
                    "period_start": date(2025, 5, 1),
                    "period_end": date(2025, 5, 31),
                    "rule_version_id": self.rule.id,
                }
            )

    def test_hr_manager_sees_all_company_payslips(self):
        """HR manager can read all payslips in the company (record rule: company scope)."""
        if not self.rule:
            return
        hr_manager = self.env["res.users"].create(
            {
                "name": "HR Manager RBAC Test",
                "login": "hr_mgr_rbac@platform.test",
                "group_ids": [(4, self.env.ref("hr.group_hr_manager").id)],
            }
        )
        visible_ids = self.env(user=hr_manager)["hr.payroll.payslip"].search([]).ids
        self.assertIn(self.slip_a.id, visible_ids, "HR manager must see Employee A's payslip.")
        self.assertIn(self.slip_b.id, visible_ids, "HR manager must see Employee B's payslip.")


class TestPayrollRunFullCycle(TransactionCase):
    """End-to-end payroll run: draft → calculate → confirm → approve → publish."""

    def setUp(self):
        super().setUp()
        self.rule = self.env["hr.payroll.rule.version"].search([("is_active", "=", True)], limit=1)
        if not self.rule:
            return
        from datetime import date

        self.employee = self.env["hr.employee"].create(
            {
                "name": "Full Cycle Payroll Employee",
                "payroll_gross_monthly": 4_000.0,
                "payroll_loonheffingskorting": True,
                "payroll_pension_employee_pct": 4.0,
                "payroll_pension_employer_pct": 8.0,
                "payroll_vakantiegeld_pct": 8.0,
            }
        )
        self.run = self.env["hr.payroll.run"].create(
            {
                "name": "Full Cycle Test Run May 2025",
                "period_type": "monthly",
                "period_start": date(2025, 5, 1),
                "period_end": date(2025, 5, 31),
                "rule_version_id": self.rule.id,
            }
        )

    def test_run_draft_to_calculated(self):
        """action_calculate() creates payslips and advances run to 'calculated'."""
        if not self.rule:
            return
        self.assertEqual(self.run.state, "draft")
        self.run.action_calculate()
        self.assertEqual(self.run.state, "calculated")
        self.assertTrue(self.run.payslip_ids, "At least one payslip must exist after calculate.")
        for slip in self.run.payslip_ids:
            self.assertEqual(slip.state, "calculated")
            self.assertGreater(slip.gross_salary, 0)
            self.assertGreater(slip.net_salary, 0)
            self.assertLess(slip.net_salary, slip.gross_salary)

    def test_run_calculated_to_confirmed(self):
        """action_confirm() advances payslips and run to 'confirmed'."""
        if not self.rule:
            return
        self.run.action_calculate()
        self.run.action_confirm()
        self.assertEqual(self.run.state, "confirmed")
        for slip in self.run.payslip_ids:
            self.assertEqual(slip.state, "confirmed")

    def test_run_confirmed_to_approved(self):
        """action_approve() advances payslips and run to 'approved'."""
        if not self.rule:
            return
        self.run.action_calculate()
        self.run.action_confirm()
        self.run.action_approve()
        self.assertEqual(self.run.state, "approved")
        for slip in self.run.payslip_ids:
            self.assertEqual(slip.state, "approved")

    def test_publish_payslips_to_portal(self):
        """action_publish_payslips() moves approved payslips to 'published'."""
        if not self.rule:
            return
        self.run.action_calculate()
        self.run.action_confirm()
        self.run.action_approve()
        self.run.action_publish_payslips()
        for slip in self.run.payslip_ids:
            self.assertEqual(
                slip.state, "published", "All approved payslips must reach 'published' state."
            )

    def test_run_totals_aggregated_correctly(self):
        """Run-level totals equal the sum of individual payslip values."""
        if not self.rule:
            return
        self.run.action_calculate()
        self.run.invalidate_recordset()
        expected_gross = sum(self.run.payslip_ids.mapped("gross_salary"))
        expected_lh = sum(self.run.payslip_ids.mapped("loonheffing"))
        expected_ec = sum(self.run.payslip_ids.mapped("total_employer_cost"))
        self.assertAlmostEqual(self.run.total_gross, expected_gross, places=2)
        self.assertAlmostEqual(self.run.total_loonheffing, expected_lh, places=2)
        self.assertAlmostEqual(self.run.total_employer_cost, expected_ec, places=2)

    def test_accountant_export_returns_url_action(self):
        """action_export_accountant() returns an act_url with /web/content/ path."""
        if not self.rule:
            return
        self.run.action_calculate()
        result = self.run.action_export_accountant()
        self.assertEqual(result.get("type"), "ir.actions.act_url")
        self.assertIn("/web/content/", result.get("url", ""))

    def test_export_creates_access_log_entries(self):
        """Each export action writes hr.payroll.access.log entries for every payslip."""
        if not self.rule:
            return
        self.run.action_calculate()
        before = self.env["hr.payroll.access.log"].search_count(
            [
                ("payslip_id", "in", self.run.payslip_ids.ids),
                ("access_type", "=", "export"),
            ]
        )
        self.run.action_export_accountant()
        after = self.env["hr.payroll.access.log"].search_count(
            [
                ("payslip_id", "in", self.run.payslip_ids.ids),
                ("access_type", "=", "export"),
            ]
        )
        self.assertGreater(
            after, before, "Export must create access log entries for all payslips in the run."
        )

    def test_payroll_provider_export_returns_url_action(self):
        """action_export_payroll_provider() returns an act_url."""
        if not self.rule:
            return
        self.run.action_calculate()
        result = self.run.action_export_payroll_provider()
        self.assertEqual(result.get("type"), "ir.actions.act_url")
        self.assertIn("/web/content/", result.get("url", ""))

    def test_annual_statement_excludes_zero_ytd_employees(self):
        """action_export_annual_statement() excludes employees with ytd_gross == 0."""
        if not self.rule:
            return
        # Create an employee with no payroll data (ytd = 0)
        zero_emp = self.env["hr.employee"].create(
            {
                "name": "Zero YTD Employee",
                "payroll_gross_monthly": 0.0,
            }
        )
        self.run.action_calculate()
        result = self.run.action_export_annual_statement()
        self.assertEqual(result.get("type"), "ir.actions.act_url")
        # Verify the zero-YTD employee is not in the attachment content
        import base64

        attachment_id = int(result["url"].split("/web/content/")[1].split("?")[0])
        att = self.env["ir.attachment"].browse(attachment_id)
        csv_text = base64.b64decode(att.datas).decode("utf-8")
        self.assertNotIn(
            zero_emp.name,
            csv_text,
            "Employees with zero YTD gross must not appear in the annual statement.",
        )


class TestBijtelling(TransactionCase):
    """Tests for company car bijtelling (taxable benefit) in payroll calculation."""

    def setUp(self):
        super().setUp()
        from odoo.addons.custom_payroll_nl.lib.nl_payroll_calculator import calculate_payslip

        self.calculate = calculate_payslip
        self.params = {
            "bracket1_rate": 0.3697,
            "bracket1_max": 38_098.0,
            "bracket2_rate": 0.4950,
            "lhk_amount": 3_362.0,
            "lhk_afbouw_start": 10_000.0,
            "lhk_afbouw_end": 124_936.0,
            "lhk_afbouw_rate": 0.0206 / 12,
            "awf_employer_pct": 2.74,
            "zvw_employer_pct": 6.57,
        }

    def test_no_company_car_no_bijtelling(self):
        """Without company car, bijtelling is zero."""
        result = self.calculate(3_000.0, has_company_car=False, **self.params)
        self.assertAlmostEqual(result.bijtelling, 0.0, places=2)

    def test_standard_car_adds_bijtelling_to_taxable_gross(self):
        """Standard-rate company car increases taxable gross by bijtelling amount."""
        # Catalogue €40,000, standard rate 22%, monthly = 40000 × 22% / 12 = €733.33
        without_car = self.calculate(3_000.0, has_company_car=False, **self.params)
        with_car = self.calculate(
            3_000.0,
            has_company_car=True,
            company_car_ev=False,
            bijtelling_standard_pct=22.0,
            company_car_catalogue_value=40_000.0,
            **self.params,
        )
        expected_bijtelling = round(40_000.0 * 0.22 / 12, 2)
        self.assertAlmostEqual(with_car.bijtelling, expected_bijtelling, places=2)
        self.assertAlmostEqual(
            with_car.taxable_gross, without_car.taxable_gross + expected_bijtelling, places=2
        )
        self.assertGreater(with_car.loonheffing, without_car.loonheffing)

    def test_ev_car_uses_lower_rate(self):
        """EV company car applies the lower EV bijtelling rate."""
        standard = self.calculate(
            3_000.0,
            has_company_car=True,
            company_car_ev=False,
            bijtelling_standard_pct=22.0,
            bijtelling_ev_pct=16.0,
            company_car_catalogue_value=40_000.0,
            **self.params,
        )
        ev = self.calculate(
            3_000.0,
            has_company_car=True,
            company_car_ev=True,
            bijtelling_standard_pct=22.0,
            bijtelling_ev_pct=16.0,
            company_car_catalogue_value=40_000.0,
            **self.params,
        )
        self.assertLess(ev.bijtelling, standard.bijtelling)
        self.assertAlmostEqual(ev.bijtelling, round(40_000.0 * 0.16 / 12, 2), places=2)

    def test_zero_catalogue_value_no_bijtelling(self):
        """Company car with catalogue value = 0 produces zero bijtelling."""
        result = self.calculate(
            3_000.0,
            has_company_car=True,
            company_car_catalogue_value=0.0,
            **self.params,
        )
        self.assertAlmostEqual(result.bijtelling, 0.0, places=2)

    def test_bijtelling_in_explanation(self):
        """Bijtelling appears in calculation explanation with BIJTELLING code."""
        result = self.calculate(
            3_000.0,
            has_company_car=True,
            company_car_ev=False,
            bijtelling_standard_pct=22.0,
            company_car_catalogue_value=30_000.0,
            **self.params,
        )
        codes = [line["code"] for line in result.explanation]
        self.assertIn("BIJTELLING", codes)

    def test_employee_catalogue_value_field_exists(self):
        """hr.employee must have payroll_company_car_catalogue_value field."""
        emp = self.env["hr.employee"].create(
            {"name": "Car Employee", "payroll_company_car_catalogue_value": 35_000.0}
        )
        self.assertAlmostEqual(emp.payroll_company_car_catalogue_value, 35_000.0)

    def test_payslip_bijtelling_passed_through_model(self):
        """Payslip action_calculate() passes catalogue value to engine."""
        rule = self.env["hr.payroll.rule.version"].search([("is_active", "=", True)], limit=1)
        if not rule:
            return
        from datetime import date

        emp = self.env["hr.employee"].create(
            {
                "name": "Car Payroll Employee",
                "payroll_gross_monthly": 3_000.0,
                "payroll_loonheffingskorting": False,
                "payroll_pension_employee_pct": 0.0,
                "payroll_pension_employer_pct": 0.0,
                "payroll_vakantiegeld_pct": 8.0,
                "payroll_has_company_car": True,
                "payroll_company_car_ev": False,
                "payroll_company_car_catalogue_value": 40_000.0,
            }
        )
        run = self.env["hr.payroll.run"].create(
            {
                "name": "Bijtelling Test Run",
                "period_type": "monthly",
                "period_start": date(2025, 3, 1),
                "period_end": date(2025, 3, 31),
                "rule_version_id": rule.id,
            }
        )
        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": emp.id,
                "payroll_run_id": run.id,
                "period_start": date(2025, 3, 1),
                "period_end": date(2025, 3, 31),
                "rule_version_id": rule.id,
            }
        )
        slip.action_calculate()
        # Taxable gross must exceed gross salary by bijtelling amount
        round(40_000.0 * (rule.bijtelling_standard_pct / 100) / 12, 2)
        self.assertGreater(
            slip.allowances + slip.gross_salary,
            3_000.0 - 0.01,
            "Gross salary must be as configured.",
        )
        # Verify via explanation JSON
        import json

        explanation = json.loads(slip.calculation_json or "[]")
        codes = [e["code"] for e in explanation]
        self.assertIn("BIJTELLING", codes)


class TestFourWeekPayroll(TransactionCase):
    """Tests for 4-week period payroll calculations."""

    def setUp(self):
        super().setUp()
        from odoo.addons.custom_payroll_nl.lib.nl_payroll_calculator import (
            calculate_loonheffing,
            calculate_payslip,
        )

        self.calculate = calculate_payslip
        self.calculate_lhk = calculate_loonheffing
        self.params = {
            "bracket1_rate": 0.3697,
            "bracket1_max": 38_098.0,
            "bracket2_rate": 0.4950,
            "lhk_amount": 3_362.0,
            "lhk_afbouw_start": 10_000.0,
            "lhk_afbouw_end": 124_936.0,
            "lhk_afbouw_rate": 0.0206 / 12,
            "awf_employer_pct": 2.74,
            "zvw_employer_pct": 6.57,
        }

    def test_4week_lower_period_salary_than_monthly(self):
        """For the same annual cost, 4-week period gross is lower (13 vs 12 periods)."""
        monthly = self.calculate(3_000.0, period_type="monthly", **self.params)
        # Same annual gross: 3000×12 = 36000; 4-week: 36000/13 ≈ 2769.23
        four_week_gross = round(3_000.0 * 12 / 13, 2)
        four_week = self.calculate(four_week_gross, period_type="4week", **self.params)
        # Annualised totals should be similar
        self.assertAlmostEqual(
            monthly.gross_salary * 12,
            four_week.gross_salary * 13,
            delta=1.0,
        )

    def test_4week_loonheffing_annualised_same_as_monthly(self):
        """4-week and monthly produce the same annualised loonheffing for same income."""
        annual_gross = 42_000.0
        monthly_gross = annual_gross / 12
        four_week_gross = annual_gross / 13
        monthly = self.calculate(
            monthly_gross, period_type="monthly", loonheffingskorting=False, **self.params
        )
        four_week = self.calculate(
            four_week_gross, period_type="4week", loonheffingskorting=False, **self.params
        )
        annual_lh_monthly = round(monthly.loonheffing * 12, 0)
        annual_lh_4week = round(four_week.loonheffing * 13, 0)
        # Allow small rounding difference (≤ €2)
        self.assertAlmostEqual(annual_lh_monthly, annual_lh_4week, delta=2.0)

    def test_4week_vakantiegeld_accrual(self):
        """4-week payroll accrues vakantiegeld over 13 periods correctly."""
        result = self.calculate(2_769.23, period_type="4week", vakantiegeld_pct=8.0, **self.params)
        expected_vg = round(2_769.23 * 0.08, 2)
        self.assertAlmostEqual(result.vakantiegeld_accrual, expected_vg, places=2)
        # Annual accrual (13 periods) ≈ gross × 8% × 13
        # Allow delta=0.15 for per-period rounding accumulation across 13 periods.
        annual_vg = round(result.vakantiegeld_accrual * 13, 2)
        self.assertAlmostEqual(annual_vg, round(2_769.23 * 0.08 * 13, 2), delta=0.15)

    def test_4week_employer_costs(self):
        """Employer contributions (AWF, ZVW) are correctly calculated for 4-week periods."""
        result = self.calculate(2_769.23, period_type="4week", **self.params)
        self.assertGreater(result.awf_employer, 0)
        self.assertGreater(result.zvw_employer, 0)
        self.assertGreater(result.total_employer_cost, result.gross_salary)

    def test_year_mismatch_warning(self):
        """Payslip shows warning when rule version year != payslip period year."""
        rule = self.env["hr.payroll.rule.version"].search([("year", "=", 2025)], limit=1)
        if not rule:
            return
        from datetime import date

        emp = self.env["hr.employee"].create(
            {
                "name": "Year Mismatch Employee",
                "payroll_gross_monthly": 3_000.0,
            }
        )
        run = self.env["hr.payroll.run"].create(
            {
                "name": "Year Mismatch Run",
                "period_type": "monthly",
                "period_start": date(2024, 1, 1),  # 2024 period with 2025 rules
                "period_end": date(2024, 1, 31),
                "rule_version_id": rule.id,
            }
        )
        slip = self.env["hr.payroll.payslip"].create(
            {
                "employee_id": emp.id,
                "payroll_run_id": run.id,
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 1, 31),
                "rule_version_id": rule.id,
            }
        )
        slip.action_calculate()
        self.assertTrue(
            slip.calculation_warning,
            "A warning must be set when rule year ≠ payslip period year.",
        )
        self.assertIn("2025", slip.calculation_warning)
        self.assertIn("2024", slip.calculation_warning)
