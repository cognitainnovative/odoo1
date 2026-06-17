"""Physical stock count workflow — start count, enter quantities, confirm adjustments."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PlatformStockCount(models.Model):
    _name = "platform.stock.count"
    _description = "Physical Stock Count"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "scheduled_date desc, name"

    name = fields.Char(required=True, default="New Count", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda s: s.env["stock.warehouse"].search(
            [("company_id", "=", s.env.company.id)], limit=1
        ),
    )
    location_id = fields.Many2one(
        "stock.location",
        "Count Location",
        help="Leave blank to count the entire warehouse stock location.",
    )
    scheduled_date = fields.Date(required=True, default=fields.Date.today)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    count_line_ids = fields.One2many("platform.stock.count.line", "count_id", "Count Lines")
    line_count = fields.Integer(compute="_compute_line_count")
    notes = fields.Text()

    @api.depends("count_line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.count_line_ids)

    def action_start_count(self):
        """Load current stock quantities from quants into count lines."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError("Count can only be started from Draft state.")
        location = self.location_id or self.warehouse_id.lot_stock_id
        quants = self.env["stock.quant"].search(
            [
                ("location_id", "child_of", location.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        existing_products = set(self.count_line_ids.mapped("product_id").ids)
        new_lines = []
        for quant in quants:
            if quant.product_id.id not in existing_products:
                new_lines.append(
                    {
                        "count_id": self.id,
                        "product_id": quant.product_id.id,
                        "lot_id": quant.lot_id.id if quant.lot_id else False,
                        "expected_qty": quant.quantity,
                        "counted_qty": quant.quantity,
                    }
                )
                existing_products.add(quant.product_id.id)
        if new_lines:
            self.env["platform.stock.count.line"].create(new_lines)
        self.write({"state": "in_progress"})
        self.message_post(body=f"Physical count started. {len(new_lines)} product line(s) loaded.")

    def action_confirm_count(self):
        """Confirm count — apply qty differences as stock adjustments and log."""
        self.ensure_one()
        if self.state != "in_progress":
            raise UserError("Count must be In Progress to confirm.")
        location = self.location_id or self.warehouse_id.lot_stock_id
        adjusted = 0
        for line in self.count_line_ids:
            diff = line.counted_qty - line.expected_qty
            if abs(diff) < 0.0001:
                continue
            self.env["stock.quant"]._update_available_quantity(
                line.product_id,
                location,
                diff,
                lot_id=line.lot_id or None,
            )
            self.env["stock.audit.log"].log(
                event_type="count_confirmed",
                product_id=line.product_id.id,
                lot_id=line.lot_id.id if line.lot_id else None,
                quantity=diff,
                location_to_id=location.id,
                origin_ref=self.name,
                notes=(
                    f"Expected: {line.expected_qty:.3f}, "
                    f"Counted: {line.counted_qty:.3f}, "
                    f"Diff: {diff:+.3f}"
                ),
            )
            adjusted += 1
        self.write({"state": "done"})
        self.message_post(body=f"Count confirmed. {adjusted} adjustment(s) posted to stock.")

    def action_cancel(self):
        if self.state == "done":
            raise UserError("A completed count cannot be cancelled.")
        self.write({"state": "cancelled"})

    @api.model
    def _cron_scheduled_counts(self):
        """Cron: auto-start counts that are scheduled for today."""
        today = fields.Date.today()
        due = self.search([("state", "=", "draft"), ("scheduled_date", "=", today)])
        for count in due:
            try:
                count.action_start_count()
            except Exception as exc:
                _logger.warning("Scheduled count %s failed to start: %s", count.name, exc)
        _logger.info("Stock count cron: started %d count(s).", len(due))


class PlatformStockCountLine(models.Model):
    _name = "platform.stock.count.line"
    _description = "Stock Count Line"
    _order = "product_id"

    count_id = fields.Many2one("platform.stock.count", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True, index=True)
    lot_id = fields.Many2one("stock.lot", "Lot/Serial")
    expected_qty = fields.Float("Expected (Book)", digits="Product Unit of Measure", readonly=True)
    counted_qty = fields.Float("Counted", digits="Product Unit of Measure")
    difference = fields.Float(
        compute="_compute_difference", store=True, digits="Product Unit of Measure"
    )
    uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", store=True)

    @api.depends("counted_qty", "expected_qty")
    def _compute_difference(self):
        for line in self:
            line.difference = line.counted_qty - line.expected_qty
