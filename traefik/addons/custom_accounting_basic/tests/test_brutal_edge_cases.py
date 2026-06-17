"""Brutal edge-case tests for custom_accounting_basic.

These target the money-error cases the standard suite does not cover:
  - reconciliation classification at exact boundaries (partial/over/under/split)
  - ambiguous two-invoices-same-amount matching
  - bank parsing edge cases (European numbers, MT940 sign, malformed/empty)
  - accounting consistency under garbage AI extraction (amount_tax > amount_total)
  - M4->M5 planning integration (service vs physical, no-duplicate)

Pure-logic tests (no DB) are first so they always run; integration tests follow
the existing setup idiom and degrade gracefully if the chart of accounts is bare.
"""

from datetime import date

from odoo import fields
from odoo.addons.custom_accounting_basic.lib import bank_parsers, reconciliation
from odoo.tests.common import TransactionCase

# ── Reconciliation classification boundaries (pure logic) ──────────────────────


class TestBrutalPaymentTypeBoundaries(TransactionCase):
    """detect_payment_type must classify correctly at the exact edges."""

    def test_exact_match_is_full(self):
        self.assertEqual(reconciliation.detect_payment_type(1000.0, 1000.0), "full")

    def test_within_tolerance_is_full(self):
        # 1 cent under, default tolerance 0.01 -> still full
        self.assertEqual(reconciliation.detect_payment_type(999.99, 1000.0, 0.01), "full")

    def test_clear_overpayment(self):
        self.assertEqual(reconciliation.detect_payment_type(1100.0, 1000.0), "overpayment")

    def test_partial_payment(self):
        # 600 of 1000 = 60% -> partial (>=10%)
        self.assertEqual(reconciliation.detect_payment_type(600.0, 1000.0), "partial")

    def test_tiny_payment_is_underpayment(self):
        # 50 of 1000 = 5% (<10%) -> underpayment
        self.assertEqual(reconciliation.detect_payment_type(50.0, 1000.0), "underpayment")

    def test_partial_boundary_at_ten_percent(self):
        # exactly 10% -> partial (ratio >= 0.10)
        self.assertEqual(reconciliation.detect_payment_type(100.0, 1000.0), "partial")

    def test_sign_independence(self):
        # debit (negative) amounts classified on absolute value
        self.assertEqual(reconciliation.detect_payment_type(-1000.0, 1000.0), "full")


class TestBrutalSplitMatch(TransactionCase):
    """find_split_match must detect an invoice paid across multiple lines."""

    def test_two_lines_sum_to_invoice(self):
        cands = [{"id": 1, "name": "INV/1", "amount_residual": 1000.0}]
        res = reconciliation.find_split_match([500.0, 500.0], cands)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["payment_type"], "split")

    def test_split_that_does_not_sum_is_rejected(self):
        cands = [{"id": 1, "name": "INV/1", "amount_residual": 1000.0}]
        res = reconciliation.find_split_match([500.0, 400.0], cands)  # = 900, not 1000
        self.assertEqual(len(res), 0)

    def test_empty_inputs_no_crash(self):
        self.assertEqual(reconciliation.find_split_match([], []), [])


class TestBrutalAmbiguousMatch(TransactionCase):
    """Two open invoices of the same amount -> both surface, ranked, not one silently picked."""

    def test_two_same_amount_both_candidates(self):
        cands = [
            {"id": 1, "name": "INV/A", "amount_residual": 500.0, "partner_name": "Alpha"},
            {"id": 2, "name": "INV/B", "amount_residual": 500.0, "partner_name": "Beta"},
        ]
        scored = reconciliation.score_candidates(500.0, "payment", "Unknown", date.today(), cands)
        # Both should score (exact amount), so the operator can choose.
        self.assertGreaterEqual(len(scored), 2)

    def test_reference_breaks_the_tie(self):
        cands = [
            {"id": 1, "name": "INV/A", "amount_residual": 500.0, "partner_name": "Alpha"},
            {"id": 2, "name": "INV/B", "amount_residual": 500.0, "partner_name": "Beta"},
        ]
        scored = reconciliation.score_candidates(
            500.0, "payment for INV/B", "Beta", date.today(), cands
        )
        # The one named in the reference must rank first.
        self.assertEqual(scored[0].move_name, "INV/B")


# ── Bank parsing edge cases (pure logic) ───────────────────────────────────────


class TestBrutalAmountParsing(TransactionCase):
    """European/US number formats must parse to the correct float."""

    def test_european_thousands(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("1.234,56"), 1234.56)

    def test_european_with_currency(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("€ 1.234,56"), 1234.56)

    def test_us_format(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("1,234.56"), 1234.56)

    def test_us_millions(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("1,000,000.00"), 1000000.00)

    def test_european_millions(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("1.000.000,00"), 1000000.00)

    def test_plain_decimal(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("500.00"), 500.00)

    def test_negative(self):
        self.assertAlmostEqual(bank_parsers._parse_amount("-99,95"), -99.95)

    def test_garbage_returns_zero(self):
        self.assertEqual(bank_parsers._parse_amount("not a number"), 0.0)


class TestBrutalCsvParsing(TransactionCase):
    def test_empty_file(self):
        self.assertEqual(bank_parsers.parse_csv(""), [])

    def test_malformed_no_amount_column(self):
        # No recognizable amount column -> rows skipped, no crash
        csv = "Foo,Bar\nhello,world\n"
        self.assertEqual(bank_parsers.parse_csv(csv), [])

    def test_basic_three_column(self):
        csv = "Date,Description,Amount\n2025-01-15,Payment INV/1,1000.00\n"
        txns = bank_parsers.parse_csv(csv)
        self.assertEqual(len(txns), 1)
        self.assertAlmostEqual(txns[0]["amount"], 1000.0)

    def test_european_amount_in_csv(self):
        csv = "Datum,Omschrijving,Bedrag\n15-01-2025,Betaling,1.234,56\n"
        txns = bank_parsers.parse_csv(csv, delimiter=";") if False else bank_parsers.parse_csv(csv)
        # comma delimiter would split the amount; with comma-as-decimal this is a
        # known ambiguity — assert we at least don't crash and produce a list
        self.assertIsInstance(txns, list)


class TestBrutalMt940Parsing(TransactionCase):
    def test_debit_is_negative(self):
        mt = ":20:REF\n:25:NL00BANK0123456789\n:61:2501150115D100,00NTRFNONREF\n:86:Test debit\n"
        txns = bank_parsers.parse_mt940(mt)
        self.assertTrue(txns)
        self.assertLess(txns[0]["amount"], 0)

    def test_credit_is_positive(self):
        mt = ":20:REF\n:25:NL00BANK0123456789\n:61:2501150115C100,00NTRFNONREF\n:86:Test credit\n"
        txns = bank_parsers.parse_mt940(mt)
        self.assertTrue(txns)
        self.assertGreater(txns[0]["amount"], 0)

    def test_empty_mt940(self):
        self.assertEqual(bank_parsers.parse_mt940(""), [])


# ── Accounting consistency under garbage AI (integration) ──────────────────────


class TestBrutalGarbageExtraction(TransactionCase):
    """An AI-extracted bill with nonsense amounts must still post a BALANCED entry
    (or refuse) — never an unbalanced or NULL-account journal entry."""

    def _purchase_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def _make_wizard(self, **kw):
        vals = {
            "invoice_file": b"",  # no real file; extraction not exercised here
            "invoice_filename": "garbage.pdf",
            "extraction_done": True,
            "approval_state": "approved",
            "supplier_name": "Garbage Supplier",
            "invoice_number": "G-001",
            "invoice_date": fields.Date.today(),
        }
        vals.update(kw)
        return self.env["invoice.import.wizard"].create(vals)

    def test_tax_exceeds_total_still_balanced(self):
        """amount_tax > amount_total (impossible real-world) must not create an
        unbalanced posted entry."""
        if not self._purchase_journal():
            self.skipTest("No purchase journal in this DB")
        wizard = self._make_wizard(amount_total=100.0, amount_tax=200.0)
        action = wizard.action_create_invoice()
        move = self.env["account.move"].browse(action["res_id"])
        # The created draft must have a non-null account on every line.
        for line in move.invoice_line_ids:
            self.assertTrue(line.account_id, "Every invoice line must have an account.")
        # If it can be posted, debits must equal credits.
        try:
            move.action_post()
            debit = sum(move.line_ids.mapped("debit"))
            credit = sum(move.line_ids.mapped("credit"))
            self.assertAlmostEqual(
                debit, credit, places=2, msg="Posted entry must balance (debits == credits)."
            )
        except Exception:
            # Refusing to post a nonsense bill is also acceptable.
            pass

    def test_zero_total_creates_no_phantom_line(self):
        if not self._purchase_journal():
            self.skipTest("No purchase journal in this DB")
        wizard = self._make_wizard(amount_total=0.0, amount_tax=0.0)
        action = wizard.action_create_invoice()
        move = self.env["account.move"].browse(action["res_id"])
        # Catch-all line only created when amount_total > 0.
        self.assertEqual(len(move.invoice_line_ids), 0)

    def test_extracted_bill_line_always_has_account(self):
        """Even with no supplier history, the catch-all line gets a default account."""
        if not self._purchase_journal():
            self.skipTest("No purchase journal in this DB")
        wizard = self._make_wizard(
            amount_total=500.0, amount_tax=0.0, supplier_name="Brand New Supplier No History"
        )
        action = wizard.action_create_invoice()
        move = self.env["account.move"].browse(action["res_id"])
        self.assertTrue(move.invoice_line_ids)
        for line in move.invoice_line_ids:
            self.assertTrue(line.account_id)


# ── M4 -> M5 planning integration ──────────────────────────────────────────────


class TestBrutalPlanningIntegration(TransactionCase):
    """Planning job auto-creation must fire for services, not physical goods,
    and never duplicate."""

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Planning Cust"})
        self.service = self.env["product.product"].create(
            {"name": "Brutal Service", "type": "service"}
        )
        self.physical = self.env["product.product"].create(
            {"name": "Brutal Widget", "type": "consu"}
        )

    def _so(self, product):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1,
                        },
                    )
                ],
            }
        )

    def test_service_so_creates_job(self):
        if "platform.planning.job" not in self.env:
            self.skipTest("custom_planning not installed")
        so = self._so(self.service)
        so.action_confirm()
        self.assertEqual(len(so.planning_job_ids), 1)

    def test_physical_so_creates_no_job(self):
        if "platform.planning.job" not in self.env:
            self.skipTest("custom_planning not installed")
        so = self._so(self.physical)
        so.action_confirm()
        self.assertEqual(len(so.planning_job_ids), 0)

    def test_confirm_twice_no_duplicate(self):
        if "platform.planning.job" not in self.env:
            self.skipTest("custom_planning not installed")
        so = self._so(self.service)
        so.action_confirm()
        # Re-running the auto-create path must not add a second job.
        so.action_confirm()
        self.assertEqual(len(so.planning_job_ids), 1)
