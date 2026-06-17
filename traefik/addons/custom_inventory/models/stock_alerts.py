"""Low-stock alerts, AI-assisted reorder suggestions, and PO creation from suggestion."""

import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockWarehouseOrderpoint(models.Model):
    """Extend reorder rules with AI-suggested quantities and one-click PO creation."""

    _inherit = "stock.warehouse.orderpoint"

    ai_suggest_enabled = fields.Boolean(
        "AI Reorder Suggestions",
        default=False,
        help="If enabled, AI analyses consumption history and suggests reorder quantities.",
    )
    ai_suggested_qty = fields.Float(
        "AI Suggested Qty", readonly=True, digits="Product Unit of Measure"
    )
    ai_suggestion_date = fields.Datetime("Suggestion Generated", readonly=True)
    ai_suggestion_reason = fields.Text("Suggestion Reasoning", readonly=True)

    def action_ai_suggest_reorder(self):
        """Generate AI reorder quantity suggestion based on stock history."""
        for rule in self:
            product = rule.product_id
            recent_moves = self.env["stock.move"].search_read(
                [
                    ("product_id", "=", product.id),
                    ("state", "=", "done"),
                    ("picking_code", "=", "outgoing"),
                ],
                ["product_uom_qty", "date"],
                limit=30,
                order="date desc",
            )
            total_out = sum(m["product_uom_qty"] for m in recent_moves)
            count = len(recent_moves)
            avg_per_move = total_out / count if count else 0

            prompt = (
                f"Product: {product.display_name}\n"
                f"Current stock: {product.qty_available:.1f} {product.uom_id.name}\n"
                f"Min qty rule: {rule.product_min_qty:.1f}\n"
                f"Max qty rule: {rule.product_max_qty:.1f}\n"
                f"Last {count} outgoing moves: avg {avg_per_move:.1f} units/move\n"
                f"Total out (last {count} moves): {total_out:.1f}\n\n"
                "Suggest an optimal reorder quantity for the next period. "
                "Reply with just a number (integer or decimal)."
            )

            result = self.env["ai.service"].call(prompt, res_model=self._name, res_id=rule.id)
            if result["ok"]:
                content = result["content"].strip()
                nums = re.findall(r"\d+(?:\.\d+)?", content)
                if nums:
                    rule.write(
                        {
                            "ai_suggested_qty": float(nums[0]),
                            "ai_suggestion_date": fields.Datetime.now(),
                            "ai_suggestion_reason": content[:500],
                        }
                    )
            # Log reorder trigger to audit log
            self.env["stock.audit.log"].log(
                event_type="reorder_triggered",
                product_id=product.id,
                quantity=rule.ai_suggested_qty,
                origin_ref=f"orderpoint/{rule.id}",
                notes=f"AI suggested qty: {rule.ai_suggested_qty}",
            )

    def action_create_po_from_suggestion(self):
        """Create a draft purchase order pre-filled with the AI-suggested quantity."""
        self.ensure_one()
        if not self.ai_suggested_qty:
            raise UserError("No AI suggestion available. Run 'Generate AI Suggestion' first.")
        product_tmpl = self.product_id.product_tmpl_id
        supplier_info = self.env["product.supplierinfo"].search(
            [("product_tmpl_id", "=", product_tmpl.id)],
            limit=1,
            order="sequence asc",
        )
        if not supplier_info or not supplier_info.partner_id:
            raise UserError(
                f"No supplier configured for {product_tmpl.name}. "
                "Add a vendor in the product's Purchase tab first."
            )
        po = self.env["purchase.order"].create(
            {
                "partner_id": supplier_info.partner_id.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_id.id,
                            "product_qty": self.ai_suggested_qty,
                            "price_unit": supplier_info.price,
                            "date_planned": fields.Datetime.now(),
                        },
                    )
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Order",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def cron_low_stock_alerts(self):
        """Cron: find products below minimum qty and send chatter alerts."""
        alert_email = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("custom_inventory.low_stock_alert_email", "")
        )
        rules = self.search([("product_min_qty", ">", 0)])
        low_stock = []
        for rule in rules:
            product = rule.product_id
            if product.qty_available <= rule.product_min_qty:
                low_stock.append(
                    {
                        "product": product.display_name,
                        "on_hand": product.qty_available,
                        "minimum": rule.product_min_qty,
                        "warehouse": rule.warehouse_id.name,
                        "product_obj": product,
                    }
                )
        if low_stock:
            _logger.info(
                "Low stock alert: %d products below minimum. Alert email: %s",
                len(low_stock),
                alert_email or "not configured",
            )
            for item in low_stock[:20]:
                product = item["product_obj"]
                if product and product.product_tmpl_id:
                    product.product_tmpl_id.message_post(
                        body=(
                            f"<b>Low Stock Alert:</b> {item['product']} has "
                            f"{item['on_hand']:.1f} units on hand "
                            f"(minimum: {item['minimum']:.1f}) "
                            f"in {item['warehouse']}."
                        )
                    )
