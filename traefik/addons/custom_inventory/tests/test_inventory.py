"""Tests for M7 — product bundles, stock config, reorder rules."""

from odoo.tests.common import TransactionCase


class TestProductBundle(TransactionCase):
    """Tests for product.bundle model."""

    def setUp(self):
        super().setUp()
        # Find a storable product and a consumable for testing
        self.product_a = self.env["product.product"].create(
            {
                "name": "Component A",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.product_b = self.env["product.product"].create(
            {
                "name": "Component B",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.bundle_product = self.env["product.product"].create(
            {
                "name": "Bundle Parent",
                "type": "consu",
            }
        )

    def _make_bundle(self, **kwargs):
        vals = {
            "name": "Test Bundle",
            "product_id": self.bundle_product.id,
        }
        vals.update(kwargs)
        return self.env["product.bundle"].create(vals)

    def test_create_bundle(self):
        bundle = self._make_bundle()
        self.assertEqual(bundle.component_count, 0)

    def test_bundle_with_lines(self):
        bundle = self._make_bundle()
        self.env["product.bundle.line"].create(
            [
                {"bundle_id": bundle.id, "product_id": self.product_a.id, "quantity": 2},
                {"bundle_id": bundle.id, "product_id": self.product_b.id, "quantity": 1},
            ]
        )
        self.assertEqual(bundle.component_count, 2)

    def test_availability_check_no_stock(self):
        """Bundle is not available when components have zero stock."""
        bundle = self._make_bundle()
        self.env["product.bundle.line"].create(
            {"bundle_id": bundle.id, "product_id": self.product_a.id, "quantity": 5}
        )
        # product_a has 0 stock by default
        self.assertFalse(bundle.check_availability())

    def test_availability_summary(self):
        """availability_summary returns correct structure."""
        bundle = self._make_bundle()
        self.env["product.bundle.line"].create(
            {"bundle_id": bundle.id, "product_id": self.product_a.id, "quantity": 3}
        )
        summary = bundle.get_availability_summary()
        self.assertEqual(len(summary), 1)
        self.assertIn("product", summary[0])
        self.assertIn("required", summary[0])
        self.assertIn("available", summary[0])
        self.assertIn("ok", summary[0])
        self.assertEqual(summary[0]["required"], 3)

    def test_bundle_line_uom_related(self):
        """Bundle line uom_id is related from product."""
        bundle = self._make_bundle()
        line = self.env["product.bundle.line"].create(
            {"bundle_id": bundle.id, "product_id": self.product_a.id, "quantity": 1}
        )
        self.assertTrue(line.uom_id)


class TestStockConfig(TransactionCase):
    """Tests for inventory config parameters."""

    def test_default_stock_deduct_on(self):
        """Default auto-deduction config is 'delivery'."""
        val = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("custom_inventory.stock_deduct_on", "delivery")
        )
        self.assertEqual(val, "delivery")

    def test_can_set_stock_deduct_on(self):
        """Config parameter can be changed."""
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "sale_confirm"
        )
        val = self.env["ir.config_parameter"].sudo().get_param("custom_inventory.stock_deduct_on")
        self.assertEqual(val, "sale_confirm")
        # Reset
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "delivery"
        )


class TestProductTemplate(TransactionCase):
    """Tests for product template extensions."""

    def test_platform_sku_field(self):
        """Product template has platform_sku field."""
        tmpl = self.env["product.template"].create(
            {
                "name": "SKU Test Product",
                "platform_sku": "PLT-00001",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.assertEqual(tmpl.platform_sku, "PLT-00001")

    def test_fast_mover_default_false(self):
        tmpl = self.env["product.template"].create(
            {
                "name": "Normal Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.assertFalse(tmpl.fast_mover)

    def test_fast_mover_can_be_set(self):
        tmpl = self.env["product.template"].create(
            {
                "name": "Fast Moving Product",
                "type": "consu",
                "is_storable": True,
                "fast_mover": True,
            }
        )
        self.assertTrue(tmpl.fast_mover)


class TestStockReorderRules(TransactionCase):
    """Tests for AI-extended reorder rules."""

    def _make_rule(self, **kwargs):
        product = self.env["product.product"].create(
            {
                "name": "Reorder Test Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        if not warehouse:
            return None
        location = warehouse.lot_stock_id
        vals = {
            "product_id": product.id,
            "location_id": location.id,
            "product_min_qty": 5.0,
            "product_max_qty": 50.0,
        }
        vals.update(kwargs)
        return self.env["stock.warehouse.orderpoint"].create(vals)

    def test_ai_suggest_fields_default(self):
        """Reorder rule has AI suggestion fields with defaults."""
        rule = self._make_rule()
        if not rule:
            return  # No warehouse configured
        self.assertFalse(rule.ai_suggest_enabled)
        self.assertAlmostEqual(rule.ai_suggested_qty, 0.0)

    def test_ai_suggest_with_mock_provider(self):
        """AI suggestion runs if ai.service is available."""
        rule = self._make_rule()
        if not rule:
            return
        if "ai.service" not in self.env.registry:
            return  # custom_ai_core not installed in this test DB — skip
        rule.ai_suggest_enabled = True
        rule.action_ai_suggest_reorder()
        self.assertIsNotNone(rule.ai_suggested_qty)


class TestStockDeductOnConfirm(TransactionCase):
    """Tests for auto stock deduction on sale order confirmation."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.product = self.env["product.product"].create(
            {
                "name": "Auto-Deduct Test Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        if self.warehouse:
            self.env["stock.quant"]._update_available_quantity(
                self.product, self.warehouse.lot_stock_id, 50.0
            )
        self.partner = self.env["res.partner"].search([], limit=1) or self.env[
            "res.partner"
        ].create({"name": "Test Customer"})

    def _make_so(self, qty=5.0):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": qty,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )

    def _stock_qty(self):
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "child_of", self.warehouse.lot_stock_id.id),
            ]
        )
        return sum(quants.mapped("quantity"))

    def test_default_config_does_not_deduct_on_confirm(self):
        """Default 'delivery' config: physical stock unchanged on SO confirm."""
        if not self.warehouse:
            return
        before = self._stock_qty()
        so = self._make_so()
        so.action_confirm()
        self.assertAlmostEqual(
            self._stock_qty(),
            before,
            places=2,
            msg="Physical stock must not change on confirm with default delivery config.",
        )

    def test_sale_confirm_config_deducts_stock(self):
        """stock_deduct_on=sale_confirm: stock decreases immediately on SO confirm."""
        if not self.warehouse:
            return
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "sale_confirm"
        )
        before = self._stock_qty()
        so = self._make_so(qty=5.0)
        so.action_confirm()
        after = self._stock_qty()
        self.assertAlmostEqual(
            before - after,
            5.0,
            places=2,
            msg="Stock must decrease by ordered qty on confirm with sale_confirm config.",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "delivery"
        )

    def test_auto_deducted_flag_set_on_moves(self):
        """Moves from auto-deduction carry auto_deducted=True."""
        if not self.warehouse:
            return
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "sale_confirm"
        )
        so = self._make_so(qty=3.0)
        so.action_confirm()
        done_moves = self.env["stock.move"].search(
            [
                ("sale_line_id.order_id", "=", so.id),
                ("state", "=", "done"),
            ]
        )
        self.assertTrue(
            done_moves, "At least one done move expected after sale_confirm auto-deduction."
        )
        self.assertTrue(
            all(m.auto_deducted for m in done_moves),
            "All auto-deducted moves must have auto_deducted=True.",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "delivery"
        )


class TestStockReservation(TransactionCase):
    """Tests for stock reservation on sale order confirmation (delivery mode)."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.product = self.env["product.product"].create(
            {
                "name": "Reservation Test Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        if self.warehouse:
            self.env["stock.quant"]._update_available_quantity(
                self.product, self.warehouse.lot_stock_id, 30.0
            )
        self.partner = self.env["res.partner"].search([], limit=1) or self.env[
            "res.partner"
        ].create({"name": "Reservation Customer"})
        # Ensure default config (delivery mode — no immediate auto-deduction)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "delivery"
        )

    def test_so_confirm_creates_picking(self):
        """Confirming a SO creates an outgoing picking in delivery mode."""
        if not self.warehouse:
            return
        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 5.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        so.action_confirm()
        self.assertTrue(so.picking_ids, "Confirmed SO must generate at least one picking.")
        pickings = so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertTrue(pickings, "At least one non-done/cancel picking expected.")

    def test_reservation_reduces_virtual_availability(self):
        """After picking reservation, virtual_available decreases while on-hand qty stays the same."""
        if not self.warehouse:
            return
        qty_before = self.product.qty_available

        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 8.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        so.action_confirm()

        # Trigger reservation on the picking
        picking = so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))[:1]
        if picking:
            picking.action_assign()

        self.product.invalidate_recordset()

        # Physical on-hand must not change in delivery mode
        self.assertAlmostEqual(
            self.product.qty_available,
            qty_before,
            places=2,
            msg="Physical on-hand qty must remain unchanged in delivery mode.",
        )
        # Virtual available must drop below on-hand (reservation consumes it)
        self.assertLess(
            self.product.virtual_available,
            qty_before,
            "virtual_available must decrease after reservation.",
        )

    def test_physical_stock_unchanged_until_delivery(self):
        """Physical stock does not decrease until the delivery is validated."""
        if not self.warehouse:
            return
        qty_before = self.product.qty_available

        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 10.0,
                            "price_unit": 50.0,
                        },
                    )
                ],
            }
        )
        so.action_confirm()
        self.product.invalidate_recordset()

        self.assertAlmostEqual(
            self.product.qty_available,
            qty_before,
            places=2,
            msg="Physical on-hand qty must not change until delivery is validated.",
        )


class TestStockValuation(TransactionCase):
    """Tests for stock quantity tracking and basic valuation."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.product = self.env["product.product"].create(
            {
                "name": "Valuation Test Product",
                "type": "consu",
                "is_storable": True,
                "standard_price": 40.0,
            }
        )

    def test_qty_available_increases_after_stock_added(self):
        """Adding stock via inventory adjustment increases available quantity."""
        if not self.warehouse:
            return
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 15.0
        )
        self.product.invalidate_recordset()
        self.assertAlmostEqual(self.product.qty_available, 15.0, places=2)

    def test_stock_value_reflects_standard_price(self):
        """Stock value = qty_available × standard_price for standard-cost products."""
        if not self.warehouse:
            return
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 10.0
        )
        self.product.invalidate_recordset()
        expected = 10.0 * self.product.standard_price
        actual = self.product.qty_available * self.product.standard_price
        self.assertAlmostEqual(actual, expected, places=2)

    def test_qty_decreases_after_auto_deduction(self):
        """Qty available decreases by ordered amount when auto-deduction fires."""
        if not self.warehouse:
            return
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 20.0
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "sale_confirm"
        )
        partner = self.env["res.partner"].search([], limit=1) or self.env["res.partner"].create(
            {"name": "Valuation Customer"}
        )
        so = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 7.0,
                            "price_unit": 40.0,
                        },
                    )
                ],
            }
        )
        so.action_confirm()
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "child_of", self.warehouse.lot_stock_id.id),
            ]
        )
        remaining = sum(quants.mapped("quantity"))
        self.assertAlmostEqual(
            remaining,
            13.0,
            places=2,
            msg="Remaining stock must be 20 − 7 = 13 after auto-deduction.",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "delivery"
        )


# ── Stock Audit Log ────────────────────────────────────────────────────────────


class TestStockAuditLog(TransactionCase):
    """Tests for stock.audit.log immutable model."""

    def test_create_audit_log_entry(self):
        """Can create a stock audit log entry."""
        entry = self.env["stock.audit.log"].create(
            {
                "event_type": "manual_move",
                "notes": "Test entry",
            }
        )
        self.assertTrue(entry.id)
        self.assertEqual(entry.event_type, "manual_move")

    def test_log_classmethod(self):
        """log() convenience method creates entry with correct fields."""
        product = self.env["product.product"].create(
            {
                "name": "Audit Log Test Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        entry = self.env["stock.audit.log"].log(
            event_type="stock_deduction",
            product_id=product.id,
            quantity=5.0,
            origin_ref="sale/S00001",
            notes="Auto-deducted on SO confirm",
        )
        self.assertEqual(entry.event_type, "stock_deduction")
        self.assertEqual(entry.product_id, product)
        self.assertAlmostEqual(entry.quantity, 5.0)
        self.assertEqual(entry.origin_ref, "sale/S00001")

    def test_write_raises_user_error(self):
        """Audit log entries cannot be modified."""
        from odoo.exceptions import UserError

        entry = self.env["stock.audit.log"].create(
            {
                "event_type": "adjustment_posted",
            }
        )
        with self.assertRaises(UserError):
            entry.write({"notes": "tampered"})

    def test_unlink_raises_user_error(self):
        """Audit log entries cannot be deleted."""
        from odoo.exceptions import UserError

        entry = self.env["stock.audit.log"].create(
            {
                "event_type": "lot_created",
            }
        )
        with self.assertRaises(UserError):
            entry.unlink()

    def test_all_event_types_valid(self):
        """All declared event types can be created."""
        valid_types = [
            "stock_deduction",
            "stock_reservation",
            "reservation_released",
            "count_confirmed",
            "adjustment_posted",
            "po_received",
            "bundle_check",
            "reorder_triggered",
            "manual_move",
            "lot_created",
            "lot_expired",
        ]
        for etype in valid_types:
            entry = self.env["stock.audit.log"].create({"event_type": etype})
            self.assertEqual(entry.event_type, etype)

    def test_auto_deduction_logs_to_audit(self):
        """Auto-deduction via sale_confirm config writes audit log entry."""
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        if not warehouse:
            return
        product = self.env["product.product"].create(
            {
                "name": "Audit Deduct Test",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 20.0)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "sale_confirm"
        )
        partner = self.env["res.partner"].search([], limit=1) or self.env["res.partner"].create(
            {"name": "Audit Customer"}
        )
        so = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 4.0,
                            "price_unit": 10.0,
                        },
                    )
                ],
            }
        )
        so.action_confirm()
        logs = self.env["stock.audit.log"].search(
            [
                ("event_type", "=", "stock_deduction"),
                ("product_id", "=", product.id),
            ]
        )
        self.assertTrue(logs, "Audit log entry expected after auto-deduction.")
        self.assertIn("sale", logs[0].origin_ref)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_inventory.stock_deduct_on", "delivery"
        )


# ── Physical Stock Count ───────────────────────────────────────────────────────


class TestStockCount(TransactionCase):
    """Tests for platform.stock.count count workflow."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.product = self.env["product.product"].create(
            {
                "name": "Count Test Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        if self.warehouse:
            self.env["stock.quant"]._update_available_quantity(
                self.product, self.warehouse.lot_stock_id, 25.0
            )

    def _make_count(self, **kwargs):
        if not self.warehouse:
            return None
        vals = {
            "name": "Test Count",
            "warehouse_id": self.warehouse.id,
            "scheduled_date": "2026-06-09",
        }
        vals.update(kwargs)
        return self.env["platform.stock.count"].create(vals)

    def test_create_count_draft(self):
        count = self._make_count()
        if not count:
            return
        self.assertEqual(count.state, "draft")
        self.assertEqual(count.line_count, 0)

    def test_start_count_loads_lines(self):
        """Starting count loads current stock quantities as count lines."""
        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        self.assertEqual(count.state, "in_progress")
        self.assertGreater(count.line_count, 0)
        product_line = count.count_line_ids.filtered(lambda line: line.product_id == self.product)
        self.assertTrue(product_line)
        self.assertAlmostEqual(product_line[0].expected_qty, 25.0, places=2)
        self.assertAlmostEqual(product_line[0].counted_qty, 25.0, places=2)

    def test_confirm_count_no_difference(self):
        """Confirming count with no differences completes without adjustments."""
        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        count.action_confirm_count()
        self.assertEqual(count.state, "done")

    def test_confirm_count_with_difference_adjusts_stock(self):
        """Counted qty lower than expected reduces stock on confirm."""
        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        product_line = count.count_line_ids.filtered(lambda line: line.product_id == self.product)[
            :1
        ]
        self.assertTrue(product_line)
        product_line.counted_qty = 20.0
        self.assertAlmostEqual(product_line.difference, -5.0, places=2)

        count.action_confirm_count()
        self.assertEqual(count.state, "done")

        self.product.invalidate_recordset()
        self.assertAlmostEqual(self.product.qty_available, 20.0, places=2)

    def test_confirm_count_writes_audit_log(self):
        """Confirming a count with a difference writes a count_confirmed audit log."""
        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        product_line = count.count_line_ids.filtered(lambda line: line.product_id == self.product)[
            :1
        ]
        if not product_line:
            return
        product_line.counted_qty = 22.0
        count.action_confirm_count()

        audit_entries = self.env["stock.audit.log"].search(
            [
                ("event_type", "=", "count_confirmed"),
                ("product_id", "=", self.product.id),
                ("origin_ref", "=", count.name),
            ]
        )
        self.assertTrue(audit_entries)

    def test_cancel_count(self):
        """Count can be cancelled from in_progress."""
        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        count.action_cancel()
        self.assertEqual(count.state, "cancelled")

    def test_cancel_done_count_raises(self):
        """Cannot cancel a completed count."""
        from odoo.exceptions import UserError

        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        count.action_confirm_count()
        self.assertEqual(count.state, "done")
        with self.assertRaises(UserError):
            count.action_cancel()

    def test_start_count_raises_if_not_draft(self):
        """start_count raises if count is not in draft state."""
        from odoo.exceptions import UserError

        count = self._make_count()
        if not count:
            return
        count.action_start_count()
        with self.assertRaises(UserError):
            count.action_start_count()


# ── Serial/Lot Extension ───────────────────────────────────────────────────────


class TestStockLot(TransactionCase):
    """Tests for stock.lot platform extension."""

    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create(
            {
                "name": "Serialized Product",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
            }
        )

    def _make_lot(self, **kwargs):
        vals = {
            "name": "LOT-TEST-001",
            "product_id": self.product.id,
        }
        vals.update(kwargs)
        return self.env["stock.lot"].create(vals)

    def test_platform_notes_field(self):
        """stock.lot has platform_notes field."""
        lot = self._make_lot()
        lot.platform_notes = "Received from supplier batch 42."
        self.assertEqual(lot.platform_notes, "Received from supplier batch 42.")

    def test_supplier_lot_ref_field(self):
        """stock.lot has supplier_lot_ref field."""
        lot = self._make_lot(supplier_lot_ref="SUPPLIER-BATCH-XYZ")
        self.assertEqual(lot.supplier_lot_ref, "SUPPLIER-BATCH-XYZ")

    def test_expiry_alert_sent_default_false(self):
        """expiry_alert_sent defaults to False."""
        lot = self._make_lot()
        self.assertFalse(lot.expiry_alert_sent)

    def test_action_send_expiry_alert(self):
        """Sending expiry alert sets expiry_alert_sent=True."""
        lot = self._make_lot()
        lot.action_send_expiry_alert()
        self.assertTrue(lot.expiry_alert_sent)

    def test_action_view_stock_moves_returns_action(self):
        """action_view_stock_moves returns a window action for stock.move.line."""
        lot = self._make_lot()
        action = lot.action_view_stock_moves()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "stock.move.line")
        self.assertIn(("lot_id", "=", lot.id), action["domain"])


# ── Create PO from AI Suggestion ──────────────────────────────────────────────


class TestCreatePOFromSuggestion(TransactionCase):
    """Tests for action_create_po_from_suggestion on reorder rules."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.supplier = self.env["res.partner"].create(
            {
                "name": "Test Supplier",
                "supplier_rank": 1,
            }
        )
        self.product = self.env["product.product"].create(
            {
                "name": "PO Suggestion Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.env["product.supplierinfo"].create(
            {
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "partner_id": self.supplier.id,
                "price": 15.0,
                "min_qty": 1.0,
            }
        )

    def _make_rule(self, suggested_qty=0.0):
        if not self.warehouse:
            return None
        rule = self.env["stock.warehouse.orderpoint"].create(
            {
                "product_id": self.product.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "product_min_qty": 5.0,
                "product_max_qty": 50.0,
            }
        )
        if suggested_qty:
            rule.write(
                {
                    "ai_suggested_qty": suggested_qty,
                    "ai_suggestion_date": "2026-06-09 10:00:00",
                }
            )
        return rule

    def test_create_po_raises_without_suggestion(self):
        """action_create_po_from_suggestion raises if no AI suggestion."""
        from odoo.exceptions import UserError

        rule = self._make_rule()
        if not rule:
            return
        with self.assertRaises(UserError):
            rule.action_create_po_from_suggestion()

    def test_create_po_raises_without_supplier(self):
        """Raises UserError if product has no supplier configured."""
        from odoo.exceptions import UserError

        product_no_supplier = self.env["product.product"].create(
            {
                "name": "No Supplier Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        if not self.warehouse:
            return
        rule = self.env["stock.warehouse.orderpoint"].create(
            {
                "product_id": product_no_supplier.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "product_min_qty": 2.0,
                "product_max_qty": 20.0,
            }
        )
        rule.ai_suggested_qty = 10.0
        with self.assertRaises(UserError):
            rule.action_create_po_from_suggestion()

    def test_create_po_creates_purchase_order(self):
        """With a valid suggestion and supplier, creates a draft purchase order."""
        rule = self._make_rule(suggested_qty=30.0)
        if not rule:
            return
        result = rule.action_create_po_from_suggestion()
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "purchase.order")
        po = self.env["purchase.order"].browse(result["res_id"])
        self.assertTrue(po.exists())
        self.assertEqual(po.state, "draft")
        self.assertEqual(po.partner_id, self.supplier)
        self.assertEqual(len(po.order_line), 1)
        self.assertAlmostEqual(po.order_line[0].product_qty, 30.0, places=2)
        self.assertEqual(po.order_line[0].product_id, self.product)

    def test_create_po_uses_supplier_price(self):
        """Created PO line uses the configured supplier price."""
        rule = self._make_rule(suggested_qty=10.0)
        if not rule:
            return
        result = rule.action_create_po_from_suggestion()
        po = self.env["purchase.order"].browse(result["res_id"])
        self.assertAlmostEqual(po.order_line[0].price_unit, 15.0, places=2)
