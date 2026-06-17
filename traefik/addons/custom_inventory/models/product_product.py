"""Extend product.product / product.template with SKU, bundle link, and document count."""

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    platform_sku = fields.Char(
        "Platform SKU",
        index=True,
        help="Your internal SKU code (separate from Odoo's internal reference).",
    )
    bundle_ids = fields.One2many(
        "product.bundle",
        "product_id",
        "Bundles",
        help="Bundles that use this product as the 'parent' bundle product.",
    )
    bundle_count = fields.Integer(compute="_compute_bundle_count")
    fast_mover = fields.Boolean(
        "Fast Mover",
        default=False,
        help="Mark this product as a fast-moving item for prioritized stock counting.",
    )
    document_count = fields.Integer(compute="_compute_document_count", string="Documents")

    def _compute_bundle_count(self):
        for tmpl in self:
            tmpl.bundle_count = self.env["product.bundle"].search_count(
                [("product_id.product_tmpl_id", "=", tmpl.id)]
            )

    def _compute_document_count(self):
        for tmpl in self:
            tmpl.document_count = self.env["ir.attachment"].search_count(
                [("res_model", "=", "product.template"), ("res_id", "=", tmpl.id)]
            )

    def action_view_documents(self):
        """Open ir.attachment list for this product template."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Product Documents",
            "res_model": "ir.attachment",
            "view_mode": "list,form",
            "domain": [
                ("res_model", "=", "product.template"),
                ("res_id", "=", self.id),
            ],
            "context": {
                "default_res_model": "product.template",
                "default_res_id": self.id,
            },
        }
