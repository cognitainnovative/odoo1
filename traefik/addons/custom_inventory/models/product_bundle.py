"""Product bundle — a product composed of other products sold together."""

from odoo import api, fields, models


class ProductBundle(models.Model):
    _name = "product.bundle"
    _description = "Product Bundle"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True)
    product_id = fields.Many2one(
        "product.product",
        "Bundle Product",
        required=True,
        domain="[('type', '=', 'consu')]",
        help="The 'virtual' product that represents this bundle in quotes/orders.",
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    active = fields.Boolean(default=True)
    bundle_line_ids = fields.One2many("product.bundle.line", "bundle_id", "Components")
    component_count = fields.Integer(compute="_compute_component_count")
    notes = fields.Text()

    @api.depends("bundle_line_ids")
    def _compute_component_count(self):
        for rec in self:
            rec.component_count = len(rec.bundle_line_ids)

    def check_availability(self):
        """Return True if all components have sufficient stock."""
        self.ensure_one()
        for line in self.bundle_line_ids:
            if getattr(line.product_id, "is_storable", False):
                available = line.product_id.qty_available
                if available < line.quantity:
                    return False
        return True

    def get_availability_summary(self) -> list[dict]:
        """Return per-component availability info."""
        result = []
        for line in self.bundle_line_ids:
            is_trackable = getattr(line.product_id, "is_storable", False)
            available = line.product_id.qty_available if is_trackable else line.quantity
            result.append(
                {
                    "product": line.product_id.display_name,
                    "required": line.quantity,
                    "available": available,
                    "ok": available >= line.quantity,
                }
            )
        return result


class ProductBundleLine(models.Model):
    _name = "product.bundle.line"
    _description = "Product Bundle Component"
    _order = "sequence, product_id"

    bundle_id = fields.Many2one("product.bundle", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", required=True, string="Component")
    quantity = fields.Float("Qty", default=1.0, digits="Product Unit of Measure")
    uom_id = fields.Many2one("uom.uom", "Unit", related="product_id.uom_id", store=True)
    qty_available = fields.Float("On Hand", related="product_id.qty_available", store=False)
