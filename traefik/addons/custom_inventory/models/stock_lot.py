"""Extend stock.lot with platform-specific fields and actions."""

from odoo import fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    platform_notes = fields.Text(
        "Platform Notes",
        help="Internal notes for this lot/serial number.",
    )
    expiry_alert_sent = fields.Boolean("Expiry Alert Sent", default=False, readonly=True)
    supplier_lot_ref = fields.Char(
        "Supplier Lot Reference",
        help="The supplier's own lot/batch reference number.",
    )

    def action_view_stock_moves(self):
        """Open stock move lines filtered to this lot."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Moves: {self.name}",
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            "domain": [("lot_id", "=", self.id)],
        }

    def action_send_expiry_alert(self):
        """Post an expiry alert on each lot's chatter."""
        for lot in self:
            expiry = getattr(lot, "expiration_date", None)
            lot.message_post(
                body=(
                    f"<b>Expiry Alert:</b> Lot <b>{lot.name}</b> for "
                    f"{lot.product_id.display_name} is expiring soon "
                    f"(use-by: {expiry or 'not set'})."
                )
            )
            lot.expiry_alert_sent = True
