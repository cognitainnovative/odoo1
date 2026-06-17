"""Extend stock.move with audit fields and auto-deduction hooks."""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    platform_origin_ref = fields.Char(
        "Platform Origin",
        help="Reference to the originating document (sale order, invoice, etc.).",
    )
    auto_deducted = fields.Boolean(
        "Auto-Deducted",
        default=False,
        readonly=True,
        help="True if this move was created by Platform's auto-deduction feature.",
    )


class SaleOrder(models.Model):
    """Auto-deduct stock on sale order confirm if configured."""

    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()
        deduct_on = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("custom_inventory.stock_deduct_on", "delivery")
        )
        if deduct_on == "sale_confirm":
            for order in self:
                try:
                    order._platform_auto_deduct_stock("sale")
                except Exception as exc:
                    _logger.warning("Auto stock deduction failed for SO %s: %s", order.name, exc)
        return res

    def _platform_auto_deduct_stock(self, origin: str):
        """Immediately validate existing pickings and write to stock audit log."""
        self.ensure_one()
        # Collect move details before validation (state may change)
        pending = []
        for picking in self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
            for move in picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
                move.platform_origin_ref = f"{origin}/{self.name}"
                move.auto_deducted = True
                pending.append(
                    {
                        "product_id": move.product_id.id,
                        "quantity": move.product_uom_qty,
                        "location_from_id": move.location_id.id,
                        "location_to_id": move.location_dest_id.id,
                    }
                )
            picking.with_context(skip_sms=True, skip_backorder=True).button_validate()

        # Write one audit log entry per distinct product move
        for entry in pending:
            self.env["stock.audit.log"].log(
                event_type="stock_deduction",
                product_id=entry["product_id"],
                quantity=entry["quantity"],
                location_from_id=entry["location_from_id"],
                location_to_id=entry["location_to_id"],
                origin_ref=f"{origin}/{self.name}",
            )


class AccountMove(models.Model):
    """Auto-deduct stock on invoice confirm if configured."""

    _inherit = "account.move"

    def action_post(self):
        res = super().action_post()
        deduct_on = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("custom_inventory.stock_deduct_on", "delivery")
        )
        if deduct_on == "invoice_confirm":
            for move in self.filtered(lambda m: m.move_type == "out_invoice"):
                try:
                    if move.invoice_origin:
                        so = self.env["sale.order"].search(
                            [("name", "=", move.invoice_origin)], limit=1
                        )
                        if so:
                            so._platform_auto_deduct_stock("invoice")
                except Exception as exc:
                    _logger.warning(
                        "Auto stock deduction failed for invoice %s: %s",
                        move.name,
                        exc,
                    )
        return res
