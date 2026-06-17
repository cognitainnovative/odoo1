"""Customer discount / loyalty tiers for rental."""

from odoo import api, fields, models


class RentalDiscountTier(models.Model):
    _name = "rental.discount.tier"
    _description = "Rental Discount Tier"
    _order = "min_annual_spend desc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    min_annual_spend = fields.Float("Min Annual Spend (€)", digits=(12, 2), default=0)
    discount_pct = fields.Float("Discount (%)", digits=(5, 2), default=0)
    description = fields.Text()
    color = fields.Integer("Kanban Color", default=0)
    active = fields.Boolean(default=True)
    requires_approval_above = fields.Float(
        "Requires Approval Above (€)",
        digits=(12, 2),
        default=0,
        help="Discount requests above this order value require manager approval.",
    )


class ResPartner(models.Model):
    """Extend res.partner with rental discount tier."""

    _inherit = "res.partner"

    rental_tier_id = fields.Many2one("rental.discount.tier", "Rental Discount Tier")
    rental_tier_override = fields.Boolean(
        "Manual Tier Override",
        help="If checked, the tier is manually set and won't be auto-updated.",
    )
    rental_annual_spend = fields.Float("Annual Rental Spend (€)", digits=(12, 2), readonly=True)
    rental_order_count = fields.Integer(compute="_compute_rental_stats")

    def _compute_rental_stats(self):
        for partner in self:
            partner.rental_order_count = self.env["rental.order"].search_count(
                [("partner_id", "=", partner.id)]
            )

    @api.model
    def cron_update_rental_tiers(self):
        """Cron: update rental discount tiers based on annual spend."""
        tiers = self.env["rental.discount.tier"].search([], order="min_annual_spend desc")
        if not tiers:
            return

        partners = self.search([("rental_tier_override", "=", False)])
        for partner in partners:
            spend = partner.rental_annual_spend
            assigned = False
            for tier in tiers:
                if spend >= tier.min_annual_spend:
                    if partner.rental_tier_id != tier:
                        partner.rental_tier_id = tier
                    assigned = True
                    break
            if not assigned:
                partner.rental_tier_id = False
