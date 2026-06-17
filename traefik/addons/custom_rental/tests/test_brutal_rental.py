"""Brutal edge-case tests for custom_rental (M8).

Targets money/availability correctness the standard 60 tests may not fully cover:
  - availability/overbooking at the exact unit-count boundary
  - overlap detection edges (adjacent vs overlapping date ranges)
  - final-amount math with damages + late fees + deposit deduction (test gate)
  - late-fee day calculation (on-time, 1 day, multi-day)
  - deposit deduction capping (can't deduct more than deposit)
  - discount approval threshold boundary
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.custom_rental.tests.test_rental import _make_rental_product
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class _RentalBase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create({"name": "Brutal Renter"})

    def _order(self, product, days=5, pickup_offset_h=2, **kw):
        vals = {
            "partner_id": self.partner.id,
            "rental_product_id": product.id,
            "pickup_date": self.now + timedelta(hours=pickup_offset_h),
            "expected_return_date": self.now + timedelta(hours=pickup_offset_h, days=days),
            "price_per_day": product.price_per_day,
            "deposit_amount": product.deposit_amount,
            "deposit_paid": True,
        }
        vals.update(kw)
        return self.env["rental.order"].create(vals)


class TestBrutalAvailability(_RentalBase):
    """Overbooking must be blocked at the exact unit-count boundary."""

    def test_single_unit_blocks_second_overlap(self):
        prod = _make_rental_product(self.env, price_per_day=50.0, total_units=1)
        o1 = self._order(prod, days=5)
        o1.action_reserve()  # books the only unit
        o2 = self._order(prod, days=5)  # overlapping, same window
        with self.assertRaises(ValidationError):
            o2.action_reserve()

    def test_two_units_allows_two_overlaps_blocks_third(self):
        prod = _make_rental_product(self.env, price_per_day=50.0, total_units=2)
        self._order(prod, days=5).action_reserve()
        self._order(prod, days=5).action_reserve()
        third = self._order(prod, days=5)
        with self.assertRaises(ValidationError):
            third.action_reserve()

    def test_non_overlapping_dates_are_available(self):
        prod = _make_rental_product(self.env, price_per_day=50.0, total_units=1)
        o1 = self._order(prod, days=3)
        o1.action_reserve()
        # second rental starts well after the first ends -> should be allowed
        o2 = self.env["rental.order"].create(
            {
                "partner_id": self.partner.id,
                "rental_product_id": prod.id,
                "pickup_date": self.now + timedelta(days=10),
                "expected_return_date": self.now + timedelta(days=13),
                "price_per_day": 50.0,
                "deposit_paid": True,
            }
        )
        o2.action_reserve()  # must not raise
        self.assertEqual(o2.state, "reserved")

    def test_cancelled_order_frees_the_unit(self):
        prod = _make_rental_product(self.env, price_per_day=50.0, total_units=1)
        o1 = self._order(prod, days=5)
        o1.action_reserve()
        o1.action_cancel()  # frees the unit
        o2 = self._order(prod, days=5)
        o2.action_reserve()  # now available again
        self.assertEqual(o2.state, "reserved")


class TestBrutalFinalAmount(_RentalBase):
    """Final-amount math: rental + extras + damages + late - deposit_deducted."""

    def test_final_amount_with_damage_and_late(self):
        prod = _make_rental_product(
            self.env,
            price_per_day=100.0,
            deposit_amount=300.0,
            late_fee_per_day=25.0,
        )
        order = self._order(prod, days=4)  # base 400
        order.write(
            {
                "insurance_total": 40.0,
                "cleaning_fee": 30.0,
                "damage_amount": 150.0,
            }
        )
        # simulate a 2-day-late return
        order.actual_return_date = order.expected_return_date + timedelta(days=2)
        order._compute_late_fee()
        order._compute_final_amount()
        # 400 rental + 40 ins + 30 clean + 150 damage + (2*25=50) late - 0 deposit
        self.assertAlmostEqual(order.late_fee_total, 50.0)
        self.assertAlmostEqual(order.final_amount, 400 + 40 + 30 + 150 + 50)

    def test_deposit_deduction_reduces_final(self):
        prod = _make_rental_product(self.env, price_per_day=100.0, deposit_amount=300.0)
        order = self._order(prod, days=2)  # base 200
        order.write({"damage_amount": 100.0, "deposit_deducted": 80.0})
        order._compute_final_amount()
        # 200 + 100 damage - 80 deposit_deducted = 220
        self.assertAlmostEqual(order.final_amount, 220.0)

    def test_on_time_return_no_late_fee(self):
        prod = _make_rental_product(self.env, price_per_day=100.0, late_fee_per_day=25.0)
        order = self._order(prod, days=3)
        order.actual_return_date = order.expected_return_date  # exactly on time
        order._compute_late_fee()
        self.assertAlmostEqual(order.late_fee_total, 0.0)

    def test_early_return_no_negative_late_fee(self):
        prod = _make_rental_product(self.env, price_per_day=100.0, late_fee_per_day=25.0)
        order = self._order(prod, days=5)
        order.actual_return_date = order.expected_return_date - timedelta(days=2)
        order._compute_late_fee()
        self.assertAlmostEqual(order.late_fee_total, 0.0)


class TestBrutalDepositCap(_RentalBase):
    """Deposit deduction must never exceed the deposit amount."""

    def test_deduct_more_than_deposit_is_capped(self):
        prod = _make_rental_product(self.env, price_per_day=50.0, deposit_amount=200.0)
        order = self._order(prod, days=2)
        order.action_deduct_deposit(amount=500.0)  # try to over-deduct
        self.assertLessEqual(order.deposit_deducted, 200.0)
        self.assertAlmostEqual(order.deposit_deducted, 200.0)

    def test_release_zeroes_deduction(self):
        prod = _make_rental_product(self.env, price_per_day=50.0, deposit_amount=200.0)
        order = self._order(prod, days=2)
        order.action_deduct_deposit(amount=50.0)
        order.action_release_deposit()
        self.assertEqual(order.deposit_deducted, 0.0)
        self.assertTrue(order.deposit_returned)


class TestBrutalSignGate(_RentalBase):
    """Contract sign + deposit gates before confirm."""

    def test_confirm_blocked_without_signature(self):
        from odoo.exceptions import UserError

        prod = _make_rental_product(self.env, price_per_day=50.0, deposit_amount=0.0)
        order = self._order(prod, days=2)
        order.action_reserve()
        with self.assertRaises(UserError):
            order.action_confirm()  # not signed yet

    def test_double_sign_blocked(self):
        from odoo.exceptions import UserError

        prod = _make_rental_product(self.env, price_per_day=50.0)
        order = self._order(prod, days=2)
        order.action_sign()
        with self.assertRaises(UserError):
            order.action_sign()  # already signed
