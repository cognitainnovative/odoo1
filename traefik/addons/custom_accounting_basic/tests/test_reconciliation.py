"""Tests for AI reconciliation scoring — including partial, split, and overpayment."""

from datetime import date

from odoo.tests.common import TransactionCase


class TestReconciliationScoring(TransactionCase):
    """Tests for lib/reconciliation.py scoring logic."""

    def setUp(self):
        super().setUp()
        from odoo.addons.custom_accounting_basic.lib.reconciliation import score_candidates

        self.score_candidates = score_candidates

    def _candidate(self, **kwargs):
        base = {
            "id": 1,
            "name": "INV/2025/001",
            "amount_residual": 1250.0,
            "partner_name": "Test Corp BV",
            "ref": "INV/2025/001",
            "partner_iban": "NL91ABNA0417164300",
            "invoice_date_due": date(2025, 1, 15),
        }
        base.update(kwargs)
        return base

    def test_exact_amount_match_scores_high(self):
        """Exact amount match gives high confidence."""
        candidates = [self._candidate()]
        results = self.score_candidates(
            stmt_amount=1250.0,
            stmt_ref="Payment INV/2025/001",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].confidence, 0.5)

    def test_exact_amount_payment_type_full(self):
        """Exact amount produces payment_type='full'."""
        candidates = [self._candidate()]
        results = self.score_candidates(
            stmt_amount=1250.0,
            stmt_ref="INV/2025/001",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        self.assertEqual(results[0].payment_type, "full")

    def test_invoice_number_in_ref_boosts_score(self):
        """Invoice number found in payment reference increases confidence."""
        candidates = [self._candidate()]
        with_ref = self.score_candidates(
            stmt_amount=1250.0,
            stmt_ref="INV/2025/001",
            stmt_partner="",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        without_ref = self.score_candidates(
            stmt_amount=1250.0,
            stmt_ref="payment received",
            stmt_partner="",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        self.assertGreater(with_ref[0].confidence, without_ref[0].confidence)

    def test_no_match_returns_empty(self):
        """Completely different amount returns no candidates."""
        candidates = [self._candidate(amount_residual=1250.0)]
        results = self.score_candidates(
            stmt_amount=0.01,
            stmt_ref="unrelated",
            stmt_partner="Unknown Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        self.assertEqual(results, [])

    def test_partial_amount_payment_type(self):
        """A partial payment is classified as 'partial'."""
        candidates = [self._candidate(amount_residual=1250.0)]
        results = self.score_candidates(
            stmt_amount=625.0,
            stmt_ref="INV/2025/001 partial",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        if results:
            self.assertEqual(results[0].payment_type, "partial")

    def test_partial_amount_scores_lower_than_full(self):
        """A partial payment gets lower confidence than a full payment."""
        candidates = [self._candidate(amount_residual=1250.0)]
        full = self.score_candidates(
            stmt_amount=1250.0,
            stmt_ref="INV/2025/001",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        partial = self.score_candidates(
            stmt_amount=625.0,
            stmt_ref="INV/2025/001 partial",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        if partial:
            self.assertLessEqual(partial[0].confidence, full[0].confidence)

    def test_overpayment_detection(self):
        """Payment larger than invoice amount is classified as 'overpayment'."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import detect_payment_type

        ptype = detect_payment_type(1300.0, 1250.0)
        self.assertEqual(ptype, "overpayment")

    def test_overpayment_still_matches(self):
        """Overpayment scenario still produces a match candidate."""
        candidates = [self._candidate(amount_residual=1250.0)]
        results = self.score_candidates(
            stmt_amount=1300.0,  # 50 EUR over invoice total
            stmt_ref="INV/2025/001",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].payment_type, "overpayment")

    def test_split_payment_detection(self):
        """Two bank line amounts that sum to invoice total are detected as split."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import find_split_match

        candidates = [self._candidate(id=1, name="INV/2025/001", amount_residual=1250.0)]
        # Two bank lines: 750 + 500 = 1250
        results = find_split_match([750.0, 500.0], candidates)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["move_name"], "INV/2025/001")
        self.assertAlmostEqual(results[0]["total"], 1250.0)
        self.assertEqual(results[0]["payment_type"], "split")

    def test_split_payment_no_match_when_sum_differs(self):
        """Split detection returns empty if amounts don't sum to invoice total."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import find_split_match

        candidates = [self._candidate(amount_residual=1250.0)]
        results = find_split_match([400.0, 400.0], candidates)
        self.assertEqual(results, [])

    def test_split_payment_three_lines(self):
        """Three bank lines summing to invoice total are detected."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import find_split_match

        candidates = [self._candidate(amount_residual=1500.0)]
        results = find_split_match([500.0, 500.0, 500.0], candidates)
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["total"], 1500.0)

    def test_detect_payment_type_full(self):
        """Exact amount is 'full'."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import detect_payment_type

        self.assertEqual(detect_payment_type(1250.0, 1250.0), "full")
        self.assertEqual(detect_payment_type(1250.005, 1250.0), "full")

    def test_detect_payment_type_underpayment(self):
        """Very small amount relative to invoice is 'underpayment'."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import detect_payment_type

        self.assertEqual(detect_payment_type(1.0, 1250.0), "underpayment")

    def test_results_sorted_by_confidence(self):
        """Results are sorted highest confidence first."""
        candidates = [
            self._candidate(id=1, name="INV/2025/001", amount_residual=1250.0),
            self._candidate(id=2, name="INV/2025/002", amount_residual=500.0),
        ]
        results = self.score_candidates(
            stmt_amount=1250.0,
            stmt_ref="INV/2025/001",
            stmt_partner="Test Corp",
            stmt_date=date(2025, 1, 15),
            candidates=candidates,
        )
        if len(results) > 1:
            self.assertGreaterEqual(results[0].confidence, results[1].confidence)

    def test_partner_name_similarity(self):
        """Partner name similarity contributes to score."""
        from odoo.addons.custom_accounting_basic.lib.reconciliation import _name_similarity

        self.assertGreater(_name_similarity("Test Corp BV", "Test Corp"), 0.5)
        self.assertAlmostEqual(_name_similarity("Apple", "Google"), 0.0)
        self.assertGreater(_name_similarity("De Vries Holding", "vries holding"), 0.5)
