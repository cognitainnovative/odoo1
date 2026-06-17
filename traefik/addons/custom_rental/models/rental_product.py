"""Rental product — extends product with rental pricing rules."""

from odoo import api, fields, models


class RentalProduct(models.Model):
    _name = "rental.product"
    _description = "Rental Product"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True)
    product_id = fields.Many2one(
        "product.product",
        "Stock Product",
        required=True,
        help="The underlying stock product tracked for availability.",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    active = fields.Boolean(default=True)
    description = fields.Text()
    image_1920 = fields.Image(related="product_id.image_1920", readonly=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    price_per_day = fields.Float("Price / Day (€)", digits=(12, 2))
    price_per_week = fields.Float("Price / Week (€)", digits=(12, 2))
    price_per_month = fields.Float("Price / Month (€)", digits=(12, 2))
    minimum_days = fields.Integer("Minimum Rental Days", default=1)
    deposit_amount = fields.Float("Deposit (€)", digits=(12, 2))
    insurance_per_day = fields.Float("Insurance / Day (€)", digits=(12, 2))
    cleaning_fee = fields.Float("Cleaning Fee (€)", digits=(12, 2))
    damage_waiver_per_day = fields.Float("Damage Waiver / Day (€)", digits=(12, 2))
    late_fee_per_day = fields.Float("Late Return Fee / Day (€)", digits=(12, 2))
    weekend_surcharge_pct = fields.Float("Weekend Surcharge (%)", digits=(5, 2))

    # ── Stock & availability ──────────────────────────────────────────────────
    total_units = fields.Integer("Total Units Available", default=1)
    active_rental_count = fields.Integer(
        compute="_compute_active_rental_count", string="Active Rentals"
    )
    available_units = fields.Integer(compute="_compute_active_rental_count")

    # ── Linked orders ─────────────────────────────────────────────────────────
    rental_order_ids = fields.One2many("rental.order", "rental_product_id", "Rental Orders")

    @api.depends("rental_order_ids", "total_units")
    def _compute_active_rental_count(self):
        for rec in self:
            active = rec.rental_order_ids.filtered(
                lambda o: o.state in ("reserved", "confirmed", "picked_up", "active")
            )
            rec.active_rental_count = len(active)
            rec.available_units = max(0, rec.total_units - len(active))

    def compute_price(
        self,
        days: int,
        include_deposit: bool = False,
        include_insurance: bool = False,
        include_cleaning: bool = False,
        include_damage_waiver: bool = False,
    ) -> float:
        """Calculate the base rental price for the given number of days."""
        self.ensure_one()
        days = max(days, self.minimum_days)

        if days >= 28 and self.price_per_month:
            months = days / 30
            base = months * self.price_per_month
        elif days >= 7 and self.price_per_week:
            weeks = days / 7
            base = weeks * self.price_per_week
        else:
            base = days * self.price_per_day

        extras = 0.0
        if include_deposit:
            extras += self.deposit_amount
        if include_insurance:
            extras += self.insurance_per_day * days
        if include_cleaning:
            extras += self.cleaning_fee
        if include_damage_waiver:
            extras += self.damage_waiver_per_day * days

        return round(base + extras, 2)

    def is_available(self, start_date, end_date, exclude_order_id=None) -> bool:
        """Check if any unit is available in the given date range."""
        self.ensure_one()
        domain = [
            ("rental_product_id", "=", self.id),
            ("state", "in", ("reserved", "confirmed", "picked_up", "active")),
            ("pickup_date", "<", end_date),
            ("expected_return_date", ">", start_date),
        ]
        if exclude_order_id:
            domain.append(("id", "!=", exclude_order_id))
        booked = self.env["rental.order"].search_count(domain)
        return booked < self.total_units
