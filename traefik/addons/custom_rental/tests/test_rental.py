"""Tests for M8 — rental lifecycle, availability, pricing, discount tiers,
signing, verification gate, stock deduction, recurring billing, tier auto-update."""

from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_rental_product(env, **kwargs):
    product = env["product.product"].create(
        {"name": "Test Rental Item", "type": "consu", "is_storable": True}
    )
    vals = {
        "name": "Test Rental Product",
        "product_id": product.id,
        "price_per_day": 50.0,
        "price_per_week": 300.0,
        "price_per_month": 1000.0,
        "deposit_amount": 500.0,
        "total_units": 2,
        "minimum_days": 1,
    }
    vals.update(kwargs)
    return env["rental.product"].create(vals)


# ── Rental Product ─────────────────────────────────────────────────────────────


class TestRentalProduct(TransactionCase):

    def setUp(self):
        super().setUp()
        self.rp = _make_rental_product(self.env)

    def test_create_rental_product(self):
        self.assertEqual(self.rp.available_units, 2)
        self.assertEqual(self.rp.active_rental_count, 0)

    def test_compute_price_daily(self):
        self.assertAlmostEqual(self.rp.compute_price(3), 150.0)

    def test_compute_price_weekly(self):
        self.assertAlmostEqual(self.rp.compute_price(7), 300.0)

    def test_compute_price_monthly(self):
        self.assertAlmostEqual(self.rp.compute_price(28), round(28 / 30 * 1000.0, 2))

    def test_compute_price_minimum_days(self):
        rp = _make_rental_product(self.env, minimum_days=3)
        self.assertAlmostEqual(rp.compute_price(1), 150.0)

    def test_compute_price_with_deposit(self):
        self.assertAlmostEqual(self.rp.compute_price(2, include_deposit=True), 600.0)

    def test_availability_initially_true(self):
        start = fields.Datetime.now() + timedelta(days=1)
        end = fields.Datetime.now() + timedelta(days=3)
        self.assertTrue(self.rp.is_available(start, end))


# ── Rental Order lifecycle ─────────────────────────────────────────────────────


class TestRentalOrder(TransactionCase):

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create({"name": "Rental Customer"})
        self.rental_product = _make_rental_product(
            self.env,
            price_per_day=100.0,
            deposit_amount=200.0,
            total_units=3,
            late_fee_per_day=20.0,
        )

    def _make_order(self, days=5, **kwargs):
        vals = {
            "partner_id": self.partner.id,
            "rental_product_id": self.rental_product.id,
            "pickup_date": self.now + timedelta(hours=2),
            "expected_return_date": self.now + timedelta(hours=2, days=days),
            "price_per_day": 100.0,
            "deposit_amount": 200.0,
            "deposit_paid": True,
        }
        vals.update(kwargs)
        return self.env["rental.order"].create(vals)

    def test_order_sequence_assigned(self):
        order = self._make_order()
        self.assertTrue(order.name.startswith("REN/"))

    def test_initial_state_draft(self):
        self.assertEqual(self._make_order().state, "draft")

    def test_rental_days_computed(self):
        self.assertEqual(self._make_order(days=5).rental_days, 5)

    def test_rental_price_computed(self):
        self.assertAlmostEqual(self._make_order(days=3).rental_price, 300.0)

    def test_discount_reduces_price(self):
        order = self._make_order(days=2, discount_pct=10.0)
        self.assertAlmostEqual(order.rental_price, 180.0)

    def test_full_lifecycle(self):
        """draft → reserved → signed → confirmed → picked_up → returned → closed."""
        order = self._make_order()
        order.action_reserve()
        self.assertEqual(order.state, "reserved")
        order.action_sign()
        self.assertTrue(order.is_signed)
        order.action_confirm()
        self.assertEqual(order.state, "confirmed")
        order.action_pickup()
        self.assertEqual(order.state, "picked_up")
        order.action_return()
        self.assertEqual(order.state, "returned")
        order.action_complete_inspection()
        self.assertEqual(order.state, "invoiced")
        order.action_close()
        self.assertEqual(order.state, "closed")

    def test_confirm_requires_signature(self):
        """Confirming without signing raises UserError."""
        order = self._make_order()
        order.action_reserve()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_confirm_requires_deposit(self):
        """Confirming without deposit raises UserError (after signing)."""
        order = self._make_order(deposit_paid=False)
        order.action_reserve()
        order.action_sign()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_availability_check_blocks_overbooking(self):
        """Cannot reserve more orders than available units (total_units=3)."""
        orders = [self._make_order() for _ in range(3)]
        for o in orders:
            o.action_reserve()
        order4 = self._make_order()
        with self.assertRaises(ValidationError):
            order4.action_reserve()

    def test_late_fee_computed(self):
        order = self._make_order(days=3)
        order.actual_return_date = order.expected_return_date + timedelta(days=2)
        order._compute_late_fee()
        self.assertAlmostEqual(order.late_fee_total, 40.0)

    def test_cancel_draft(self):
        order = self._make_order()
        order.action_cancel()
        self.assertEqual(order.state, "cancelled")

    def test_cannot_cancel_active(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_confirm()
        order.action_pickup()
        with self.assertRaises(UserError):
            order.action_cancel()

    def test_deposit_deduction(self):
        order = self._make_order()
        order.action_deduct_deposit(100.0)
        self.assertAlmostEqual(order.deposit_deducted, 100.0)

    def test_final_amount_includes_damage(self):
        order = self._make_order(days=2, damage_amount=150.0)
        self.assertAlmostEqual(order.final_amount, 350.0)


# ── Signing step ───────────────────────────────────────────────────────────────


class TestSigningStep(TransactionCase):

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create({"name": "Signing Customer"})
        self.rental_product = _make_rental_product(self.env)

    def _make_order(self, **kwargs):
        vals = {
            "partner_id": self.partner.id,
            "rental_product_id": self.rental_product.id,
            "pickup_date": self.now + timedelta(days=1),
            "expected_return_date": self.now + timedelta(days=4),
            "deposit_paid": True,
        }
        vals.update(kwargs)
        return self.env["rental.order"].create(vals)

    def test_unsigned_by_default(self):
        order = self._make_order()
        self.assertFalse(order.is_signed)

    def test_action_sign_sets_is_signed(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        self.assertTrue(order.is_signed)
        self.assertTrue(order.signed_date)
        self.assertEqual(order.signed_by_id, self.env.user)

    def test_action_sign_posts_chatter(self):
        order = self._make_order()
        order.action_reserve()
        msg_count_before = len(order.message_ids)
        order.action_sign()
        self.assertGreater(len(order.message_ids), msg_count_before)
        bodies = " ".join(m.body or "" for m in order.message_ids)
        self.assertIn("Contract Signed", bodies)

    def test_double_sign_raises(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        with self.assertRaises(UserError):
            order.action_sign()

    def test_confirm_blocked_without_signature(self):
        order = self._make_order()
        order.action_reserve()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_confirm_succeeds_after_signature(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_confirm()
        self.assertEqual(order.state, "confirmed")


# ── Verification gate ──────────────────────────────────────────────────────────


class TestVerificationGate(TransactionCase):

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create({"name": "Verify Customer"})
        self.rental_product = _make_rental_product(self.env)

    def _make_order(self, **kwargs):
        vals = {
            "partner_id": self.partner.id,
            "rental_product_id": self.rental_product.id,
            "pickup_date": self.now + timedelta(days=1),
            "expected_return_date": self.now + timedelta(days=4),
            "deposit_paid": True,
        }
        vals.update(kwargs)
        return self.env["rental.order"].create(vals)

    def test_pickup_allowed_without_verification_record(self):
        """When no verification_id is set, pickup proceeds normally."""
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_confirm()
        order.action_pickup()
        self.assertEqual(order.state, "picked_up")

    def test_pickup_blocked_when_verification_pending(self):
        """Pickup is blocked when a verification record is pending."""
        verification = self.env["rental.verification"].create(
            {"partner_id": self.partner.id, "verification_type": "id_document"}
        )
        self.assertEqual(verification.status, "pending")
        order = self._make_order(verification_id=verification.id)
        order.action_reserve()
        order.action_sign()
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_pickup()

    def test_pickup_allowed_after_verification_verified(self):
        """Pickup proceeds once the verification record is set to verified."""
        verification = self.env["rental.verification"].create(
            {"partner_id": self.partner.id, "verification_type": "kvk"}
        )
        verification.action_verify()
        self.assertEqual(verification.status, "verified")
        order = self._make_order(verification_id=verification.id)
        order.action_reserve()
        order.action_sign()
        order.action_confirm()
        order.action_pickup()
        self.assertEqual(order.state, "picked_up")

    def test_pickup_blocked_when_verification_expired(self):
        """Pickup blocked when the verification is expired."""
        verification = self.env["rental.verification"].create(
            {"partner_id": self.partner.id, "verification_type": "passport"}
        )
        verification.action_verify()
        verification.action_expire()
        order = self._make_order(verification_id=verification.id)
        order.action_reserve()
        order.action_sign()
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_pickup()


# ── Discount tiers ─────────────────────────────────────────────────────────────


class TestDiscountTiers(TransactionCase):

    def test_tiers_seeded(self):
        codes = set(self.env["rental.discount.tier"].search([]).mapped("code"))
        self.assertIn("standard", codes)
        self.assertIn("silver", codes)
        self.assertIn("gold", codes)
        self.assertIn("platinum", codes)
        self.assertIn("negotiated", codes)

    def test_silver_discount(self):
        silver = self.env["rental.discount.tier"].search([("code", "=", "silver")], limit=1)
        self.assertAlmostEqual(silver.discount_pct, 5.0)

    def test_gold_discount_higher_than_silver(self):
        silver = self.env["rental.discount.tier"].search([("code", "=", "silver")], limit=1)
        gold = self.env["rental.discount.tier"].search([("code", "=", "gold")], limit=1)
        self.assertGreater(gold.discount_pct, silver.discount_pct)


# ── Discount approval audit ────────────────────────────────────────────────────


class TestDiscountApprovalAudit(TransactionCase):

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create({"name": "Discount Customer"})
        self.rental_product = _make_rental_product(self.env, price_per_day=200.0)

    def _make_order(self, **kwargs):
        vals = {
            "partner_id": self.partner.id,
            "rental_product_id": self.rental_product.id,
            "pickup_date": self.now + timedelta(days=1),
            "expected_return_date": self.now + timedelta(days=5),
            "price_per_day": 200.0,
            "discount_pct": 15.0,
            "discount_type": "volume",
            "discount_reason": "Large volume booking",
        }
        vals.update(kwargs)
        return self.env["rental.order"].create(vals)

    def test_approve_discount_sets_approved_flag(self):
        order = self._make_order()
        order.action_approve_discount()
        self.assertTrue(order.discount_approved)
        self.assertEqual(order.discount_approver_id, self.env.user)

    def test_approve_discount_posts_chatter(self):
        order = self._make_order()
        order.action_approve_discount()
        bodies = " ".join(m.body or "" for m in order.message_ids)
        self.assertIn("Discount Approved", bodies)
        self.assertIn("15.0%", bodies)
        self.assertIn("Large volume booking", bodies)

    def test_approve_discount_includes_approver_name(self):
        order = self._make_order()
        order.action_approve_discount()
        bodies = " ".join(m.body or "" for m in order.message_ids)
        self.assertIn(self.env.user.name, bodies)


# ── Verification model ─────────────────────────────────────────────────────────


class TestRentalVerification(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Verify Me"})

    def _make_v(self, **kwargs):
        vals = {"partner_id": self.partner.id, "verification_type": "id_document"}
        vals.update(kwargs)
        return self.env["rental.verification"].create(vals)

    def test_create_verification(self):
        self.assertEqual(self._make_v().status, "pending")

    def test_verify_action(self):
        v = self._make_v()
        v.action_verify()
        self.assertEqual(v.status, "verified")
        self.assertTrue(v.verified_date)

    def test_reject_action(self):
        v = self._make_v()
        v.action_reject()
        self.assertEqual(v.status, "rejected")

    def test_expire_cron(self):
        v = self._make_v()
        v.action_verify()
        v.expiry_date = date.today() - timedelta(days=1)
        self.env["rental.verification"].cron_expire_verifications()
        self.assertEqual(v.status, "expired")


# ── Full lifecycle (E2E) ───────────────────────────────────────────────────────


class TestRentalFullCycle(TransactionCase):

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.stock_product = self.env["product.product"].create(
            {"name": "E2E Rental Item", "type": "consu", "is_storable": True}
        )
        self.rental_product = self.env["rental.product"].create(
            {
                "name": "E2E Rental Product",
                "product_id": self.stock_product.id,
                "price_per_day": 50.0,
                "deposit_amount": 200.0,
                "minimum_days": 1,
                "total_units": 5,
            }
        )
        self.partner = self.env["res.partner"].create(
            {"name": "Rental E2E Customer", "email": "rental@e2e.test"}
        )
        # Seed 5 units in stock so deductions have something to work with
        if self.warehouse:
            self.env["stock.quant"]._update_available_quantity(
                self.stock_product, self.warehouse.lot_stock_id, 5.0
            )
        # Ensure a sale journal exists for invoice creation
        if not self.env["account.journal"].search([("type", "=", "sale")], limit=1):
            self.env["account.journal"].create(
                {
                    "name": "Customer Invoices",
                    "code": "INV",
                    "type": "sale",
                    "company_id": self.env.company.id,
                }
            )
        # Ensure products have an income account (fresh DB has no chart of accounts)
        if not self.env["account.account"].search([("account_type", "=", "income")], limit=1):
            income_account = self.env["account.account"].create(
                {
                    "name": "Test Income",
                    "code": "400001",
                    "account_type": "income",
                }
            )
        else:
            income_account = self.env["account.account"].search(
                [("account_type", "=", "income")], limit=1
            )
        self.rental_product.product_id.product_tmpl_id.property_account_income_id = income_account
        # Ensure a receivable account exists (needed for payment_term invoice line)
        if not self.env["account.account"].search(
            [("account_type", "=", "asset_receivable")], limit=1
        ):
            receivable_account = self.env["account.account"].create(
                {
                    "name": "Test Receivable",
                    "code": "120001",
                    "account_type": "asset_receivable",
                    "reconcile": True,
                }
            )
        else:
            receivable_account = self.env["account.account"].search(
                [("account_type", "=", "asset_receivable")], limit=1
            )
        self.partner.property_account_receivable_id = receivable_account

    def _make_order(self, days=3, **kwargs):
        vals = {
            "partner_id": self.partner.id,
            "rental_product_id": self.rental_product.id,
            "pickup_date": self.now + timedelta(hours=1),
            "expected_return_date": self.now + timedelta(days=days, hours=1),
            "price_per_day": self.rental_product.price_per_day,
            "deposit_amount": self.rental_product.deposit_amount,
        }
        vals.update(kwargs)
        return self.env["rental.order"].create(vals)

    def _stock_qty(self):
        if not self.warehouse:
            return 0.0
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.stock_product.id),
                ("location_id", "child_of", self.warehouse.lot_stock_id.id),
            ]
        )
        return sum(quants.mapped("quantity"))

    def test_full_rental_cycle_no_damage(self):
        """Full happy path including sign step."""
        order = self._make_order(days=3)
        self.assertEqual(order.state, "draft")

        order.action_reserve()
        self.assertEqual(order.state, "reserved")

        order.action_sign()
        self.assertTrue(order.is_signed)

        order.action_record_deposit_paid()
        self.assertTrue(order.deposit_paid)

        order.action_confirm()
        self.assertEqual(order.state, "confirmed")

        order.action_pickup()
        self.assertEqual(order.state, "picked_up")

        order.action_activate()
        self.assertEqual(order.state, "active")

        order.action_return()
        self.assertEqual(order.state, "returned")
        self.assertTrue(order.actual_return_date)

        order.action_complete_inspection()
        self.assertEqual(order.state, "invoiced")

        result = order.action_create_invoice()
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertTrue(order.invoice_id)

        order.action_close()
        self.assertEqual(order.state, "closed")

    def test_blocked_stock_during_rental(self):
        """Stock decreases on pickup and returns to original level on return."""
        if not self.warehouse:
            return
        qty_before = self._stock_qty()

        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_record_deposit_paid()
        order.action_confirm()
        order.action_pickup()
        self.assertEqual(order.state, "picked_up")

        # Stock must be deducted by 1 immediately on pickup
        self.stock_product.invalidate_recordset()
        qty_after_pickup = self._stock_qty()
        self.assertAlmostEqual(
            qty_before - qty_after_pickup,
            1.0,
            places=2,
            msg="Stock must decrease by 1 on rental pickup.",
        )

        # Return the item — stock must be restored
        order.action_return()
        self.stock_product.invalidate_recordset()
        qty_after_return = self._stock_qty()
        self.assertAlmostEqual(
            qty_after_return,
            qty_before,
            places=2,
            msg="Stock must return to original level after rental return.",
        )

    def test_confirm_requires_deposit_paid(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_cancel_after_reservation(self):
        order = self._make_order()
        order.action_reserve()
        order.action_cancel()
        self.assertEqual(order.state, "cancelled")

    def test_cannot_cancel_active_rental(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_record_deposit_paid()
        order.action_confirm()
        order.action_pickup()
        order.action_activate()
        with self.assertRaises(UserError):
            order.action_cancel()

    def test_deposit_partial_deduction_on_damage(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_record_deposit_paid()
        order.action_confirm()
        order.action_pickup()
        order.action_return()
        order.action_deduct_deposit(100.0)
        self.assertAlmostEqual(order.deposit_deducted, 100.0, places=2)
        self.assertFalse(order.deposit_returned)

    def test_deposit_full_release_on_clean_return(self):
        order = self._make_order()
        order.action_reserve()
        order.action_sign()
        order.action_record_deposit_paid()
        order.action_confirm()
        order.action_pickup()
        order.action_return()
        order.action_release_deposit()
        self.assertTrue(order.deposit_returned)
        self.assertAlmostEqual(order.deposit_deducted, 0.0, places=2)

    def test_invoice_includes_damage_and_late_fee(self):
        """Invoice line equals final_amount which includes damage and late fee."""
        rental_product = self.env["rental.product"].create(
            {
                "name": "Late Fee Product",
                "product_id": self.stock_product.id,
                "price_per_day": 50.0,
                "deposit_amount": 100.0,
                "total_units": 5,
                "late_fee_per_day": 25.0,
            }
        )
        order = self.env["rental.order"].create(
            {
                "partner_id": self.partner.id,
                "rental_product_id": rental_product.id,
                "pickup_date": self.now + timedelta(hours=1),
                "expected_return_date": self.now + timedelta(days=3, hours=1),
                "price_per_day": 50.0,
                "deposit_amount": 100.0,
            }
        )
        order.action_reserve()
        order.action_sign()
        order.action_record_deposit_paid()
        order.action_confirm()
        order.action_pickup()
        order.action_return()  # sets actual_return_date = now()

        # Simulate 2-day late return by overriding actual_return_date after the return action
        late_date = order.expected_return_date + timedelta(days=2)
        order.write({"actual_return_date": late_date, "damage_amount": 75.0})
        order._compute_late_fee()
        order._compute_final_amount()

        order.action_complete_inspection()
        order.action_create_invoice()

        invoice = order.invoice_id
        self.assertTrue(invoice)
        total_invoiced = sum(invoice.invoice_line_ids.mapped("price_unit"))
        self.assertAlmostEqual(total_invoiced, order.final_amount, places=2)
        self.assertGreater(order.final_amount, order.rental_price)
        # late fee = 2 × 25 = 50; damage = 75; base = 3 × 50 = 150 → total 275
        self.assertAlmostEqual(order.final_amount, 275.0, places=2)


# ── Recurring rental billing ───────────────────────────────────────────────────


class TestRecurringRental(TransactionCase):

    def setUp(self):
        super().setUp()
        self.now = fields.Datetime.now()
        self.partner = self.env["res.partner"].create({"name": "Recurring Customer"})
        self.rental_product = _make_rental_product(self.env, price_per_day=100.0, total_units=5)
        # Ensure a sale journal exists for invoice creation
        if not self.env["account.journal"].search([("type", "=", "sale")], limit=1):
            self.env["account.journal"].create(
                {
                    "name": "Customer Invoices",
                    "code": "INV",
                    "type": "sale",
                    "company_id": self.env.company.id,
                }
            )
        # Ensure products have an income account (fresh DB has no chart of accounts)
        if not self.env["account.account"].search([("account_type", "=", "income")], limit=1):
            income_account = self.env["account.account"].create(
                {
                    "name": "Test Income",
                    "code": "400001",
                    "account_type": "income",
                }
            )
        else:
            income_account = self.env["account.account"].search(
                [("account_type", "=", "income")], limit=1
            )
        self.rental_product.product_id.product_tmpl_id.property_account_income_id = income_account
        # Ensure a receivable account exists (needed for payment_term invoice line)
        if not self.env["account.account"].search(
            [("account_type", "=", "asset_receivable")], limit=1
        ):
            receivable_account = self.env["account.account"].create(
                {
                    "name": "Test Receivable",
                    "code": "120001",
                    "account_type": "asset_receivable",
                    "reconcile": True,
                }
            )
        else:
            receivable_account = self.env["account.account"].search(
                [("account_type", "=", "asset_receivable")], limit=1
            )
        self.partner.property_account_receivable_id = receivable_account

    def _make_recurring_order(self, interval="weekly", last_invoice_days_ago=None):
        order = self.env["rental.order"].create(
            {
                "partner_id": self.partner.id,
                "rental_product_id": self.rental_product.id,
                "pickup_date": self.now - timedelta(days=30),
                "expected_return_date": self.now + timedelta(days=30),
                "price_per_day": 100.0,
                "deposit_amount": 0.0,
                "deposit_paid": True,
                "state": "active",
                "is_recurring": True,
                "recurring_interval": interval,
            }
        )
        if last_invoice_days_ago is not None:
            order.last_invoice_date = date.today() - timedelta(days=last_invoice_days_ago)
        return order

    def test_recurring_invoice_created_when_due_weekly(self):
        """Cron creates invoice when 7+ days have elapsed since last invoice."""
        self._make_recurring_order(interval="weekly", last_invoice_days_ago=8)
        invoice_count_before = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.env["rental.order"].cron_generate_recurring_billing()
        invoice_count_after = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.assertGreater(
            invoice_count_after,
            invoice_count_before,
            "Recurring invoice must be created when billing period is elapsed.",
        )

    def test_recurring_skips_when_not_due(self):
        """Cron does not create invoice when billing period has not elapsed."""
        self._make_recurring_order(interval="weekly", last_invoice_days_ago=2)
        invoice_count_before = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.env["rental.order"].cron_generate_recurring_billing()
        invoice_count_after = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.assertEqual(
            invoice_count_after,
            invoice_count_before,
            "Cron must not create invoice when billing period has not elapsed.",
        )

    def test_last_invoice_date_advances_after_billing(self):
        """After recurring billing runs, last_invoice_date is updated to today."""
        order = self._make_recurring_order(interval="weekly", last_invoice_days_ago=8)
        self.env["rental.order"].cron_generate_recurring_billing()
        self.assertEqual(order.last_invoice_date, date.today())

    def test_no_last_invoice_date_triggers_first_billing(self):
        """Order with no last_invoice_date always gets its first recurring invoice."""
        self._make_recurring_order(interval="monthly")
        # last_invoice_date is False — cron should create first invoice
        invoice_count_before = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.env["rental.order"].cron_generate_recurring_billing()
        invoice_count_after = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.assertGreater(invoice_count_after, invoice_count_before)

    def test_non_recurring_order_not_billed(self):
        """Non-recurring active orders are never billed by recurring cron."""
        self.env["rental.order"].create(
            {
                "partner_id": self.partner.id,
                "rental_product_id": self.rental_product.id,
                "pickup_date": self.now - timedelta(days=10),
                "expected_return_date": self.now + timedelta(days=10),
                "price_per_day": 100.0,
                "deposit_paid": True,
                "state": "active",
                "is_recurring": False,
            }
        )
        invoice_count_before = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.env["rental.order"].cron_generate_recurring_billing()
        invoice_count_after = self.env["account.move"].search_count(
            [("partner_id", "=", self.partner.id), ("move_type", "=", "out_invoice")]
        )
        self.assertEqual(invoice_count_after, invoice_count_before)


# ── Tier auto-update ───────────────────────────────────────────────────────────


class TestTierAutoUpdate(TransactionCase):

    def setUp(self):
        super().setUp()
        self.standard = self.env["rental.discount.tier"].search(
            [("code", "=", "standard")], limit=1
        )
        self.silver = self.env["rental.discount.tier"].search([("code", "=", "silver")], limit=1)
        self.gold = self.env["rental.discount.tier"].search([("code", "=", "gold")], limit=1)
        self.platinum = self.env["rental.discount.tier"].search(
            [("code", "=", "platinum")], limit=1
        )

    def _make_partner(self, spend=0.0, override=False):
        partner = self.env["res.partner"].create({"name": f"Tier Partner {spend}"})
        partner.rental_annual_spend = spend
        partner.rental_tier_override = override
        return partner

    def test_partner_with_low_spend_gets_low_tier(self):
        """Partner with spend below silver threshold gets a 0%-discount tier."""
        partner = self._make_partner(spend=500.0)
        self.env["res.partner"].cron_update_rental_tiers()
        # Both 'standard' and 'negotiated' have min=0 and discount_pct=0;
        # cron picks whichever comes first — assert discount is 0%, not silver+.
        self.assertAlmostEqual(partner.rental_tier_id.discount_pct, 0.0)

    def test_partner_promoted_to_silver_when_spend_exceeds_threshold(self):
        """Partner with spend ≥ 1000 gets silver tier."""
        partner = self._make_partner(spend=1500.0)
        self.env["res.partner"].cron_update_rental_tiers()
        self.assertEqual(partner.rental_tier_id, self.silver)

    def test_partner_promoted_to_gold_when_spend_exceeds_threshold(self):
        """Partner with spend ≥ 5000 gets gold tier."""
        partner = self._make_partner(spend=7500.0)
        self.env["res.partner"].cron_update_rental_tiers()
        self.assertEqual(partner.rental_tier_id, self.gold)

    def test_partner_promoted_to_platinum(self):
        """Partner with spend ≥ 20000 gets platinum tier."""
        partner = self._make_partner(spend=25000.0)
        self.env["res.partner"].cron_update_rental_tiers()
        self.assertEqual(partner.rental_tier_id, self.platinum)

    def test_partner_with_override_not_updated(self):
        """Partner with rental_tier_override=True is skipped by cron."""
        partner = self._make_partner(spend=50000.0, override=True)
        # Manually pin to silver so we have a clear before/after comparison
        partner.rental_tier_id = self.silver
        self.env["res.partner"].cron_update_rental_tiers()
        # Despite huge spend, the tier must stay at silver (not be promoted)
        self.assertEqual(partner.rental_tier_id, self.silver)

    def test_tier_applies_correct_discount(self):
        """silver tier gives 5% discount; gold gives 10%."""
        if self.silver:
            self.assertAlmostEqual(self.silver.discount_pct, 5.0)
        if self.gold:
            self.assertAlmostEqual(self.gold.discount_pct, 10.0)
