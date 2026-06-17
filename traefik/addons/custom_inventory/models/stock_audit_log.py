"""Immutable stock audit log — records all inventory events."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_EVENT_TYPES = [
    ("stock_deduction", "Stock Deduction"),
    ("stock_reservation", "Stock Reserved"),
    ("reservation_released", "Reservation Released"),
    ("count_confirmed", "Physical Count Confirmed"),
    ("adjustment_posted", "Stock Adjustment"),
    ("po_received", "Purchase Order Received"),
    ("bundle_check", "Bundle Availability Checked"),
    ("reorder_triggered", "Reorder Rule Triggered"),
    ("manual_move", "Manual Stock Move"),
    ("lot_created", "Lot/Serial Created"),
    ("lot_expired", "Lot Expired"),
]


class StockAuditLog(models.Model):
    _name = "stock.audit.log"
    _description = "Stock Audit Log"
    _order = "create_date desc, id desc"
    _rec_name = "event_type"

    event_type = fields.Selection(_EVENT_TYPES, required=True, readonly=True)
    product_id = fields.Many2one("product.product", readonly=True, index=True)
    lot_id = fields.Many2one("stock.lot", "Lot/Serial", readonly=True)
    quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    location_from_id = fields.Many2one("stock.location", "From Location", readonly=True)
    location_to_id = fields.Many2one("stock.location", "To Location", readonly=True)
    origin_ref = fields.Char("Origin Reference", readonly=True)
    user_id = fields.Many2one(
        "res.users", "Performed By", readonly=True, default=lambda s: s.env.user
    )
    company_id = fields.Many2one("res.company", readonly=True, default=lambda s: s.env.company)
    notes = fields.Text(readonly=True)
    create_date = fields.Datetime(readonly=True)

    def write(self, vals):
        raise UserError("Stock audit log entries are immutable and cannot be modified.")

    def unlink(self):
        raise UserError("Stock audit log entries cannot be deleted.")

    @api.model
    def log(
        self,
        event_type,
        product_id=None,
        lot_id=None,
        quantity=None,
        location_from_id=None,
        location_to_id=None,
        origin_ref=None,
        notes=None,
    ):
        """Convenience classmethod — create a stock audit log entry."""
        return self.create(
            {
                "event_type": event_type,
                "product_id": product_id,
                "lot_id": lot_id,
                "quantity": quantity,
                "location_from_id": location_from_id,
                "location_to_id": location_to_id,
                "origin_ref": origin_ref,
                "user_id": self.env.user.id,
                "company_id": self.env.company.id,
                "notes": notes,
            }
        )
