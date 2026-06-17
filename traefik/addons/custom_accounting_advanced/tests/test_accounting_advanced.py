"""Tests for M11 — fiscal years, period locks, fixed assets, BV annual accounts, reports."""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestPeriodLock(TransactionCase):
    """Test gate: period-lock prevents posting; reversal correction path."""

    def _get_general_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )

    def _make_move(self, move_date=None):
        journal = self._get_general_journal()
        if not journal:
            self.skipTest("No general journal found in test company")
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": move_date or date(2024, 6, 1),
            }
        )

    def test_period_lock_prevents_cancel(self):
        """button_cancel raises UserError for a move dated in a locked period."""
        move = self._make_move(move_date=date(2024, 6, 1))
        self.env.company.fiscalyear_lock_date = date(2024, 12, 31)
        try:
            with self.assertRaises(UserError):
                move.button_cancel()
        finally:
            self.env.company.fiscalyear_lock_date = False

    def test_move_after_lock_date_not_blocked(self):
        """button_cancel does NOT raise for a move dated after the lock date."""
        move = self._make_move(move_date=date(2025, 3, 1))
        self.env.company.fiscalyear_lock_date = date(2024, 12, 31)
        try:
            # Should not raise — period is not locked
            try:
                move.button_cancel()
            except UserError as e:
                if "locked period" in str(e):
                    self.fail("button_cancel raised period-lock error for an unlocked period")
        finally:
            self.env.company.fiscalyear_lock_date = False

    def test_reversal_reason_field_stored(self):
        """platform_reversal_reason is persisted on account.move."""
        move = self._make_move()
        move.platform_reversal_reason = "Incorrect account — corrected by reversal entry"
        self.assertEqual(
            move.platform_reversal_reason,
            "Incorrect account — corrected by reversal entry",
        )

    def test_period_lock_override_requires_reason(self):
        """action_override_period_lock raises UserError when reason is blank."""
        with self.assertRaises(UserError):
            self.env.company.action_override_period_lock(reason="")

    def test_period_lock_override_records_audit_trail(self):
        """action_override_period_lock stores reason, date, and user on company."""
        company = self.env.company
        company.action_override_period_lock(reason="Year-end adjustment approved by CFO")
        self.assertEqual(
            company.platform_lock_override_reason,
            "Year-end adjustment approved by CFO",
        )
        self.assertEqual(company.platform_lock_override_by, self.env.user)
        self.assertTrue(company.platform_lock_override_date)


class TestAccrualProvision(TransactionCase):
    """Tests for account.accrual.provision model."""

    def _get_account(self):
        return self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )

    def _make_accrual(self, entry_type="accrual", **kwargs):
        account = self._get_account()
        if not account:
            self.skipTest("No expense account found in test company")
        vals = {
            "name": "Test Accrual",
            "entry_type": entry_type,
            "amount": 1_000.0,
            "account_id": account.id,
            "period_start": date(2025, 1, 1),
        }
        vals.update(kwargs)
        return self.env["account.accrual.provision"].create(vals)

    def test_create_accrual(self):
        rec = self._make_accrual()
        self.assertEqual(rec.state, "draft")
        self.assertEqual(rec.entry_type, "accrual")

    def test_create_prepayment(self):
        rec = self._make_accrual(entry_type="prepayment")
        self.assertEqual(rec.entry_type, "prepayment")

    def test_create_provision(self):
        rec = self._make_accrual(entry_type="provision")
        self.assertEqual(rec.entry_type, "provision")

    def test_post_accrual(self):
        rec = self._make_accrual()
        rec.action_post()
        self.assertEqual(rec.state, "posted")

    def test_post_raises_if_already_posted(self):
        rec = self._make_accrual()
        rec.action_post()
        with self.assertRaises(UserError):
            rec.action_post()

    def test_reverse_accrual(self):
        rec = self._make_accrual()
        rec.action_post()
        rec.action_reverse()
        self.assertEqual(rec.state, "reversed")

    def test_reverse_raises_if_draft(self):
        rec = self._make_accrual()
        with self.assertRaises(UserError):
            rec.action_reverse()


class TestFiscalYear(TransactionCase):
    """Tests for custom fiscal year model."""

    def _make_fy(self, year=2025, **kwargs):
        vals = {
            "name": f"FY {year}",
            "date_from": date(year, 1, 1),
            "date_to": date(year, 12, 31),
        }
        vals.update(kwargs)
        return self.env["account.fiscal.year.custom"].create(vals)

    def test_create_fiscal_year(self):
        fy = self._make_fy()
        self.assertEqual(fy.state, "open")

    def test_lock_fiscal_year(self):
        fy = self._make_fy()
        fy.action_lock()
        self.assertEqual(fy.state, "locked")

    def test_close_requires_closing_entries(self):
        """Closing without marking closing_entries_done raises UserError."""
        fy = self._make_fy()
        fy.action_lock()
        with self.assertRaises(UserError):
            fy.action_close()

    def test_close_after_closing_entries(self):
        fy = self._make_fy()
        fy.action_lock()
        fy.closing_entries_done = True
        fy.action_close()
        self.assertEqual(fy.state, "closed")

    def test_reopen(self):
        fy = self._make_fy()
        fy.action_lock()
        fy.action_reopen()
        self.assertEqual(fy.state, "open")

    def test_year_company_unique(self):
        """Same year + date range is unique per company."""
        import psycopg2
        from odoo.tools import mute_logger

        self._make_fy(year=2024)
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self._make_fy(year=2024)


class TestFixedAsset(TransactionCase):
    """Tests for fixed asset model."""

    def _make_asset(self, **kwargs):
        vals = {
            "name": "Test Machine",
            "category": "machinery",
            "acquisition_date": date(2023, 1, 1),
            "acquisition_value": 10_000.0,
            "residual_value": 1_000.0,
            "useful_life_years": 5,
            "depreciation_method": "straight_line",
        }
        vals.update(kwargs)
        return self.env["account.fixed.asset"].create(vals)

    def test_create_asset(self):
        asset = self._make_asset()
        self.assertEqual(asset.state, "draft")

    def test_annual_depreciation_straight_line(self):
        """Annual depreciation = (cost - residual) / useful_life."""
        asset = self._make_asset()
        expected = (10_000.0 - 1_000.0) / 5
        self.assertAlmostEqual(asset.annual_depreciation, expected)

    def test_net_book_value_initial(self):
        """NBV = acquisition_value when no depreciation posted."""
        asset = self._make_asset()
        self.assertAlmostEqual(asset.net_book_value, 10_000.0)

    def test_depreciation_schedule_generated(self):
        """generate_depreciation_schedule creates correct number of lines."""
        asset = self._make_asset()
        asset.action_start()
        asset.generate_depreciation_schedule()
        self.assertEqual(len(asset.depreciation_line_ids), 5)

    def test_depreciation_schedule_totals(self):
        """Sum of depreciation lines = acquisition_value - residual_value."""
        asset = self._make_asset()
        asset.action_start()
        asset.generate_depreciation_schedule()
        total_dep = sum(line.depreciation_amount for line in asset.depreciation_line_ids)
        self.assertAlmostEqual(total_dep, 10_000.0 - 1_000.0, places=1)

    def test_dispose_asset(self):
        asset = self._make_asset()
        asset.action_start()
        asset.action_dispose(disposal_value=5_000.0)
        self.assertEqual(asset.state, "disposed")
        self.assertAlmostEqual(asset.disposal_value, 5_000.0)


class TestBvAnnualAccounts(TransactionCase):
    """Tests for BV annual accounts model."""

    def _make_annual(self, year=2024):
        return self.env["bv.annual.accounts"].create(
            {
                "name": f"Annual Accounts {year}",
                "fiscal_year": year,
                "total_revenue": 500_000.0,
                "total_expenses": 350_000.0,
                "retained_earnings_start": 100_000.0,
            }
        )

    def test_create_annual_accounts(self):
        rec = self._make_annual()
        self.assertEqual(rec.state, "draft")

    def test_net_result_computed(self):
        rec = self._make_annual()
        self.assertAlmostEqual(rec.net_result, 500_000.0 - 350_000.0)

    def test_retained_earnings_computed(self):
        rec = self._make_annual()
        rec.dividends = 50_000.0
        expected = 100_000.0 + rec.net_result - 50_000.0
        self.assertAlmostEqual(rec.retained_earnings_end, expected)

    def test_submit_requires_accountant(self):
        """Cannot submit for review without assigning an accountant."""
        rec = self._make_annual()
        with self.assertRaises(UserError):
            rec.action_submit_for_review()

    def test_full_workflow(self):
        """draft → review → approved → filed."""
        rec = self._make_annual()
        rec.write({"accountant_id": self.env.user.id})
        rec.action_submit_for_review()
        self.assertEqual(rec.state, "review")
        rec.action_approve()
        self.assertEqual(rec.state, "approved")
        rec.action_file()
        self.assertEqual(rec.state, "filed")


class TestAccountBudget(TransactionCase):
    """Tests for simplified budget model."""

    def test_create_budget(self):
        budget = self.env["account.budget.platform"].create(
            {
                "name": "2025 Budget",
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        self.assertEqual(budget.state, "draft")
        self.assertAlmostEqual(budget.total_budget, 0.0)

    def test_budget_with_lines(self):
        budget = self.env["account.budget.platform"].create(
            {
                "name": "Budget Test",
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        account = self.env["account.account"].search([("account_type", "=", "expense")], limit=1)
        self.env["account.budget.line.platform"].create(
            [
                {
                    "budget_id": budget.id,
                    "name": "Line 1",
                    "account_id": account.id if account else False,
                    "budgeted_amount": 10_000.0,
                },
                {"budget_id": budget.id, "name": "Line 2", "budgeted_amount": 5_000.0},
            ]
        )
        self.assertAlmostEqual(budget.total_budget, 15_000.0)


class TestAuditExport(TransactionCase):
    """Tests for audit-file export wizard."""

    def test_create_wizard(self):
        wizard = self.env["account.audit.export.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
                "export_format": "csv",
            }
        )
        self.assertEqual(wizard.export_format, "csv")

    def test_export_csv_generates_attachment(self):
        """Export CSV creates an attachment and returns act_url."""
        wizard = self.env["account.audit.export.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
                "export_format": "csv",
            }
        )
        result = wizard.action_export()
        self.assertEqual(result.get("type"), "ir.actions.act_url")

    def test_debit_credit_invariant(self):
        """All posted moves have balanced debit = credit per entry."""
        moves = self.env["account.move"].search(
            [("state", "=", "posted"), ("company_id", "=", self.env.company.id)],
            limit=100,
        )
        for move in moves:
            total_debit = sum(move.line_ids.mapped("debit"))
            total_credit = sum(move.line_ids.mapped("credit"))
            self.assertAlmostEqual(
                total_debit,
                total_credit,
                places=2,
                msg=f"Move {move.name} is not balanced: debit={total_debit}, credit={total_credit}",
            )


# ── Critical Gap: Opening/Closing Entry Automation ────────────────────────────


class TestFiscalYearEntries(TransactionCase):
    """Test gate: fiscal year opening balance and closing entries automation."""

    def _make_fy(self, year=2025, **kwargs):
        vals = {
            "name": f"FY {year}",
            "date_from": date(year, 1, 1),
            "date_to": date(year, 12, 31),
        }
        vals.update(kwargs)
        return self.env["account.fiscal.year.custom"].create(vals)

    def _get_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def test_opening_entries_raises_if_already_done(self):
        fy = self._make_fy()
        fy.opening_balance_done = True
        with self.assertRaises(UserError):
            fy.action_create_opening_entries()

    def test_closing_entries_raises_if_already_done(self):
        fy = self._make_fy()
        fy.closing_entries_done = True
        with self.assertRaises(UserError):
            fy.action_create_closing_entries()

    def test_closing_entries_raises_without_pl_data(self):
        """Closing entries on a year with no posted P&L moves raises UserError."""
        fy = self._make_fy(year=2020)
        with self.assertRaises(UserError):
            fy.action_create_closing_entries()

    def test_opening_entries_raises_without_prior_balances(self):
        """Opening entries on a year with no prior balance data raises UserError."""
        fy = self._make_fy(year=2020)
        with self.assertRaises(UserError):
            fy.action_create_opening_entries()

    def test_opening_balance_move_created(self):
        """Opening entries action creates a draft move when prior data exists."""
        journal = self._get_journal()
        asset_account = self.env["account.account"].search(
            [("account_type", "=", "asset_cash"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )
        liability_account = self.env["account.account"].search(
            [
                ("account_type", "=", "liability_current"),
                ("company_ids", "in", [self.env.company.id]),
            ],
            limit=1,
        )
        if not (journal and asset_account and liability_account):
            self.skipTest("Required accounts/journal not found in test company")

        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2024, 12, 31),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": asset_account.id,
                            "name": "Cash",
                            "debit": 5000.0,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": liability_account.id,
                            "name": "Loan",
                            "debit": 0.0,
                            "credit": 5000.0,
                        },
                    ),
                ],
            }
        )
        move.action_post()

        fy = self._make_fy(year=2025)
        fy.action_create_opening_entries()

        self.assertTrue(fy.opening_balance_done)
        self.assertTrue(fy.opening_balance_move_id)
        self.assertEqual(fy.opening_balance_move_id.state, "draft")

    def test_closing_entries_created_with_pl_data(self):
        """Closing entries action creates a balanced move when P&L data exists."""
        journal = self._get_journal()
        income_acct = self.env["account.account"].search(
            [("account_type", "=", "income"), ("company_ids", "in", [self.env.company.id])], limit=1
        )
        expense_acct = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )
        retained_acct = self.env["account.account"].search(
            [
                ("account_type", "=", "equity_unaffected"),
                ("company_ids", "in", [self.env.company.id]),
            ],
            limit=1,
        )
        if not (journal and income_acct and expense_acct and retained_acct):
            self.skipTest("Required accounts not found in test company")

        # Seed: balanced P&L entry (income 1000, expense 600, equity 400)
        seeded = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2025, 6, 1),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": income_acct.id,
                            "name": "Revenue",
                            "debit": 0.0,
                            "credit": 1000.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": expense_acct.id,
                            "name": "Expense",
                            "debit": 600.0,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": retained_acct.id,
                            "name": "Balance",
                            "debit": 400.0,
                            "credit": 0.0,
                        },
                    ),
                ],
            }
        )
        seeded.action_post()

        fy = self._make_fy(year=2025)
        fy.action_create_closing_entries()

        self.assertTrue(fy.closing_entries_done)
        self.assertTrue(fy.closing_entries_move_id)
        # Verify the created move contains P&L lines
        closing_move = fy.closing_entries_move_id
        account_ids_in_move = closing_move.line_ids.mapped("account_id.id")
        self.assertIn(income_acct.id, account_ids_in_move)
        self.assertIn(expense_acct.id, account_ids_in_move)


# ── Critical Gap: Debit=Credit Constraint ─────────────────────────────────────


class TestDebitCreditConstraint(TransactionCase):
    """Test gate: action_post() enforces debit=credit for general journal entries."""

    def _get_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def _get_account(self):
        return self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )

    def test_action_post_rejects_unbalanced_entry(self):
        """action_post() raises UserError when debit ≠ credit on a general entry."""
        journal = self._get_journal()
        account = self._get_account()
        if not (journal and account):
            self.skipTest("Required journal/account not found in test company")

        from odoo.tools import mute_logger

        with self.assertRaises(UserError), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                move = self.env["account.move"].create(
                    {
                        "journal_id": journal.id,
                        "date": date(2025, 1, 1),
                        "line_ids": [
                            (
                                0,
                                0,
                                {
                                    "account_id": account.id,
                                    "name": "Unbalanced debit-only line",
                                    "debit": 100.0,
                                    "credit": 0.0,
                                },
                            )
                        ],
                    }
                )
                move.action_post()

    def test_action_post_allows_balanced_entry(self):
        """action_post() does not raise for a balanced general entry."""
        journal = self._get_journal()
        account = self._get_account()
        if not (journal and account):
            self.skipTest("Required journal/account not found in test company")

        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2025, 1, 1),
                "line_ids": [
                    (0, 0, {"account_id": account.id, "name": "Dr", "debit": 100.0, "credit": 0.0}),
                    (0, 0, {"account_id": account.id, "name": "Cr", "debit": 0.0, "credit": 100.0}),
                ],
            }
        )
        # Should not raise period-lock or balance error
        try:
            move.action_post()
        except UserError as e:
            if "debit" in str(e).lower() and "credit" in str(e).lower():
                self.fail(f"Balanced entry incorrectly rejected: {e}")


# ── Critical Gap: Accrual Reversal Creates GL Entry ───────────────────────────


class TestAccrualReversalGL(TransactionCase):
    """Test gate: action_reverse() on an accrual creates an actual account.move."""

    def _make_posted_accrual(self):
        account = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )
        if not account:
            self.skipTest("No expense account in test company")
        rec = self.env["account.accrual.provision"].create(
            {
                "name": "GL Reversal Test",
                "entry_type": "accrual",
                "amount": 500.0,
                "account_id": account.id,
                "period_start": date(2025, 1, 1),
            }
        )
        rec.action_post()
        return rec

    def test_reverse_creates_gl_entry(self):
        rec = self._make_posted_accrual()
        rec.action_reverse()
        self.assertEqual(rec.state, "reversed")
        self.assertTrue(rec.reversal_move_id, "Reversal must create a GL journal entry")
        self.assertIsInstance(rec.reversal_move_id.id, int)

    def test_reverse_gl_entry_references_accrual(self):
        rec = self._make_posted_accrual()
        rec.action_reverse()
        move = rec.reversal_move_id
        self.assertIn(rec.name, move.ref or "")

    def test_cron_auto_reverse(self):
        """cron_auto_reverse() reverses all accruals with auto_reverse_date <= today."""
        rec = self._make_posted_accrual()
        rec.auto_reverse_date = date(2025, 1, 1)
        self.env["account.accrual.provision"].cron_auto_reverse()
        self.assertEqual(rec.state, "reversed")

    def test_cron_does_not_reverse_future_date(self):
        """cron_auto_reverse() leaves accruals with future auto_reverse_date untouched."""
        rec = self._make_posted_accrual()
        rec.auto_reverse_date = date(2099, 12, 31)
        self.env["account.accrual.provision"].cron_auto_reverse()
        self.assertEqual(rec.state, "posted")


# ── Report Wizards ─────────────────────────────────────────────────────────────


class TestTrialBalance(TransactionCase):

    def test_create_wizard(self):
        w = self.env["account.trial.balance.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        self.assertTrue(w.id)

    def test_generate_returns_action(self):
        w = self.env["account.trial.balance.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        result = w.action_generate()
        self.assertEqual(result.get("type"), "ir.actions.act_window")

    def test_generate_with_posted_data(self):
        """Trial balance generates lines when posted moves exist."""
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)], limit=1
        )
        account = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )
        if not (journal and account):
            self.skipTest("Required setup not found")
        self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2025, 3, 1),
                "line_ids": [
                    (0, 0, {"account_id": account.id, "name": "D", "debit": 100.0, "credit": 0.0}),
                    (0, 0, {"account_id": account.id, "name": "C", "debit": 0.0, "credit": 100.0}),
                ],
            }
        ).action_post()
        w = self.env["account.trial.balance.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        w.action_generate()
        self.assertTrue(len(w.line_ids) > 0)


class TestGeneralLedger(TransactionCase):

    def test_create_wizard(self):
        w = self.env["account.general.ledger.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        self.assertTrue(w.id)

    def test_generate_returns_action(self):
        w = self.env["account.general.ledger.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        result = w.action_generate()
        self.assertEqual(result.get("type"), "ir.actions.act_window")

    def test_account_filter(self):
        """Wizard accepts an optional account filter without errors."""
        account = self.env["account.account"].search(
            [("company_ids", "in", [self.env.company.id])], limit=1
        )
        if not account:
            self.skipTest("No account in test company")
        w = self.env["account.general.ledger.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
                "account_id": account.id,
            }
        )
        result = w.action_generate()
        self.assertEqual(result.get("res_model"), "account.general.ledger.wizard")


class TestAgedBalance(TransactionCase):

    def test_create_wizard_receivable(self):
        w = self.env["account.aged.balance.wizard"].create(
            {
                "date_at": date(2025, 12, 31),
                "aged_type": "receivable",
            }
        )
        self.assertEqual(w.aged_type, "receivable")

    def test_create_wizard_payable(self):
        w = self.env["account.aged.balance.wizard"].create(
            {
                "date_at": date(2025, 12, 31),
                "aged_type": "payable",
            }
        )
        self.assertEqual(w.aged_type, "payable")

    def test_generate_returns_action(self):
        w = self.env["account.aged.balance.wizard"].create(
            {
                "date_at": date(2025, 12, 31),
            }
        )
        result = w.action_generate()
        self.assertEqual(result.get("type"), "ir.actions.act_window")


class TestVatSummary(TransactionCase):

    def test_create_wizard(self):
        w = self.env["account.vat.summary.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        self.assertTrue(w.id)

    def test_generate_returns_action(self):
        w = self.env["account.vat.summary.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        result = w.action_generate()
        self.assertEqual(result.get("type"), "ir.actions.act_window")

    def test_generate_no_error_without_tax_lines(self):
        """Wizard runs without error when there are no tax lines in the period."""
        w = self.env["account.vat.summary.wizard"].create(
            {
                "date_from": date(2020, 1, 1),
                "date_to": date(2020, 12, 31),
            }
        )
        w.action_generate()
        self.assertEqual(len(w.line_ids), 0)


class TestCashFlow(TransactionCase):

    def test_create_wizard(self):
        w = self.env["account.cash.flow.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        self.assertTrue(w.id)

    def test_generate_returns_action(self):
        w = self.env["account.cash.flow.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        result = w.action_generate()
        self.assertEqual(result.get("type"), "ir.actions.act_window")

    def test_generate_sets_totals(self):
        w = self.env["account.cash.flow.wizard"].create(
            {
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 12, 31),
            }
        )
        w.action_generate()
        # Fields are computed; no type error
        self.assertIsInstance(w.net_cash_flow, float)


# ── Cost Centre ────────────────────────────────────────────────────────────────


class TestCostCentre(TransactionCase):

    def test_create_cost_centre(self):
        cc = self.env["account.cost.centre"].create(
            {
                "name": "IT Department",
                "code": "IT-001",
            }
        )
        self.assertEqual(cc.name, "IT Department")
        self.assertTrue(cc.active)

    def test_cost_centre_code_unique(self):
        import psycopg2
        from odoo.tools import mute_logger

        self.env["account.cost.centre"].create({"name": "Finance", "code": "FIN-001"})
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["account.cost.centre"].create({"name": "Finance2", "code": "FIN-001"})

    def test_parent_child_hierarchy(self):
        parent = self.env["account.cost.centre"].create({"name": "Operations", "code": "OPS"})
        child = self.env["account.cost.centre"].create(
            {
                "name": "Logistics",
                "code": "OPS-LOG",
                "parent_id": parent.id,
            }
        )
        self.assertEqual(child.parent_id, parent)
        self.assertIn(child, parent.child_ids)

    def test_cost_centre_on_move_line(self):
        """account.move.line can store a cost_centre_id."""
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)], limit=1
        )
        account = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", [self.env.company.id])],
            limit=1,
        )
        if not (journal and account):
            self.skipTest("Required setup not found")

        cc = self.env["account.cost.centre"].create({"name": "Project X", "code": "PRJ-X"})
        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2025, 1, 1),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": "Cost",
                            "debit": 100.0,
                            "credit": 0.0,
                            "cost_centre_id": cc.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": "Offset",
                            "debit": 0.0,
                            "credit": 100.0,
                        },
                    ),
                ],
            }
        )
        line_with_cc = move.line_ids.filtered(lambda line: line.cost_centre_id)
        self.assertEqual(len(line_with_cc), 1)
        self.assertEqual(line_with_cc.cost_centre_id, cc)


# ── Chart of Accounts Extension ───────────────────────────────────────────────


class TestCoaExtension(TransactionCase):

    def test_coa_fields_exist(self):
        """account.account has the platform extension fields."""
        account = self.env["account.account"].search(
            [("company_ids", "in", [self.env.company.id])], limit=1
        )
        if not account:
            self.skipTest("No account in test company")
        # Fields must exist without AttributeError
        _ = account.is_reconcilable_platform
        _ = account.platform_account_group
        _ = account.external_ref
        _ = account.account_notes

    def test_coa_fields_writable(self):
        account = self.env["account.account"].search(
            [("company_ids", "in", [self.env.company.id])], limit=1
        )
        if not account:
            self.skipTest("No account in test company")
        account.write(
            {
                "is_reconcilable_platform": True,
                "platform_account_group": "operating",
                "external_ref": "EXT-001",
            }
        )
        self.assertTrue(account.is_reconcilable_platform)
        self.assertEqual(account.platform_account_group, "operating")
        self.assertEqual(account.external_ref, "EXT-001")

    def test_cost_centre_default_on_account(self):
        account = self.env["account.account"].search(
            [("company_ids", "in", [self.env.company.id])], limit=1
        )
        if not account:
            self.skipTest("No account in test company")
        cc = self.env["account.cost.centre"].create({"name": "Default CC", "code": "DEF-CC"})
        account.cost_centre_default_id = cc
        self.assertEqual(account.cost_centre_default_id, cc)
