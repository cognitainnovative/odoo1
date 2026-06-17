"""Rental Order — full lifecycle from quote to deposit release."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class RentalOrder(models.Model):
    _name = "rental.order"
    _description = "Rental Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "pickup_date desc, name"
    _rec_name = "name"

    name = fields.Char("Reference", default="New", copy=False, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)

    # ── Core references ───────────────────────────────────────────────────────
    partner_id = fields.Many2one("res.partner", "Customer", required=True, index=True)
    rental_product_id = fields.Many2one(
        "rental.product", "Rental Product", required=True, index=True
    )
    user_id = fields.Many2one("res.users", "Sales Person", default=lambda s: s.env.user)
    sale_order_id = fields.Many2one("sale.order", "Linked Sale Order", ondelete="set null")
    invoice_id = fields.Many2one("account.move", "Final Invoice", ondelete="set null")

    # ── State machine ─────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ("draft", "Draft / Quote"),
            ("reserved", "Reserved"),
            ("confirmed", "Confirmed — Awaiting Pickup"),
            ("picked_up", "Picked Up"),
            ("active", "Active"),
            ("return_pending", "Return Pending"),
            ("returned", "Returned — Inspection"),
            ("invoiced", "Invoiced"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    pickup_date = fields.Datetime("Pickup Date", required=True, tracking=True)
    expected_return_date = fields.Datetime("Expected Return Date", required=True, tracking=True)
    actual_return_date = fields.Datetime("Actual Return Date", readonly=True)
    rental_days = fields.Integer("Rental Days", compute="_compute_rental_days", store=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    price_per_day = fields.Float("Price / Day (€)", digits=(12, 2))
    rental_price = fields.Float(
        "Rental Price (€)", compute="_compute_prices", store=True, digits=(12, 2)
    )
    deposit_amount = fields.Float("Deposit (€)", digits=(12, 2))
    deposit_paid = fields.Boolean("Deposit Paid", default=False)
    deposit_returned = fields.Boolean("Deposit Returned", default=False)
    deposit_deducted = fields.Float("Deposit Deducted (€)", digits=(12, 2), default=0.0)
    insurance_total = fields.Float("Insurance (€)", digits=(12, 2))
    cleaning_fee = fields.Float("Cleaning Fee (€)", digits=(12, 2))
    damage_waiver_total = fields.Float("Damage Waiver (€)", digits=(12, 2))
    late_fee_total = fields.Float("Late Fee (€)", compute="_compute_late_fee", store=False)
    damage_amount = fields.Float("Damage Cost (€)", digits=(12, 2), default=0.0)
    final_amount = fields.Float(
        "Final Total (€)", compute="_compute_final_amount", store=True, digits=(12, 2)
    )

    # ── Discount ──────────────────────────────────────────────────────────────
    discount_pct = fields.Float("Discount (%)", digits=(5, 2), default=0.0, tracking=True)
    discount_reason = fields.Char("Discount Reason", tracking=True)
    discount_type = fields.Selection(
        [
            ("tier", "Tier Discount"),
            ("category", "Category Discount"),
            ("duration", "Duration Discount"),
            ("volume", "Volume Discount"),
            ("project", "Project Discount"),
            ("other", "Other"),
        ],
        string="Discount Type",
        tracking=True,
    )
    discount_approved = fields.Boolean("Discount Approved", default=False, readonly=True)
    discount_approver_id = fields.Many2one("res.users", "Approved By", readonly=True)
    discount_requires_approval = fields.Boolean(
        compute="_compute_discount_requires_approval", store=False
    )

    # ── Signing ───────────────────────────────────────────────────────────────
    is_signed = fields.Boolean("Contract Signed", default=False, tracking=True, readonly=True)
    signed_by_id = fields.Many2one("res.users", "Signed By", readonly=True)
    signed_date = fields.Datetime("Signed On", readonly=True)

    # ── Recurring billing ─────────────────────────────────────────────────────
    is_recurring = fields.Boolean("Recurring Rental", default=False, tracking=True)
    recurring_interval = fields.Selection(
        [("weekly", "Weekly"), ("monthly", "Monthly")],
        string="Billing Interval",
    )
    last_invoice_date = fields.Date("Last Invoice Date", readonly=True)

    # ── Verification ──────────────────────────────────────────────────────────
    verification_id = fields.Many2one("rental.verification", "Verification Record")
    verification_status = fields.Selection(
        related="verification_id.status", string="Verification Status", store=True
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text("Notes / Special Conditions")
    damage_description = fields.Text("Damage Description")
    return_notes = fields.Text("Return / Inspection Notes")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("rental.order") or "New"
        return super().create(vals_list)

    # ── Computed fields ───────────────────────────────────────────────────────

    @api.depends("pickup_date", "expected_return_date")
    def _compute_rental_days(self):
        for order in self:
            if order.pickup_date and order.expected_return_date:
                delta = order.expected_return_date - order.pickup_date
                order.rental_days = max(1, delta.days)
            else:
                order.rental_days = 0

    @api.depends(
        "rental_days", "price_per_day", "discount_pct", "pickup_date", "expected_return_date"
    )
    def _compute_prices(self):
        for order in self:
            base = order.rental_days * order.price_per_day
            if (
                order.rental_product_id
                and order.rental_product_id.weekend_surcharge_pct
                and order.pickup_date
                and order.expected_return_date
            ):
                from datetime import timedelta

                weekend_days = sum(
                    1
                    for i in range(order.rental_days)
                    if (order.pickup_date.date() + timedelta(days=i)).isoweekday() in (6, 7)
                )
                if weekend_days:
                    surcharge = (
                        weekend_days
                        * order.price_per_day
                        * order.rental_product_id.weekend_surcharge_pct
                        / 100
                    )
                    base += surcharge
            if order.discount_pct:
                base *= 1 - order.discount_pct / 100
            order.rental_price = round(base, 2)

    @api.depends("actual_return_date", "expected_return_date")
    def _compute_late_fee(self):
        for order in self:
            if (
                order.actual_return_date
                and order.expected_return_date
                and order.actual_return_date > order.expected_return_date
            ):
                late_days = (
                    order.actual_return_date.date() - order.expected_return_date.date()
                ).days
                late_per_day = (
                    order.rental_product_id.late_fee_per_day if order.rental_product_id else 0
                )
                order.late_fee_total = late_days * late_per_day
            else:
                order.late_fee_total = 0.0

    @api.depends(
        "rental_price",
        "deposit_amount",
        "deposit_deducted",
        "insurance_total",
        "cleaning_fee",
        "damage_waiver_total",
        "late_fee_total",
        "damage_amount",
    )
    def _compute_final_amount(self):
        for order in self:
            order.final_amount = (
                order.rental_price
                + order.insurance_total
                + order.cleaning_fee
                + order.damage_waiver_total
                + order.late_fee_total
                + order.damage_amount
                - order.deposit_deducted
            )

    @api.depends("discount_pct", "final_amount", "partner_id.rental_tier_id")
    def _compute_discount_requires_approval(self):
        for order in self:
            tier = order.partner_id.rental_tier_id
            threshold = tier.requires_approval_above if tier else 0
            if threshold and order.discount_pct > 0 and order.final_amount > threshold:
                order.discount_requires_approval = True
            else:
                order.discount_requires_approval = False

    # ── onchange: populate pricing from rental product ────────────────────────

    @api.onchange("rental_product_id")
    def _onchange_rental_product(self):
        if self.rental_product_id:
            prod = self.rental_product_id
            self.price_per_day = prod.price_per_day
            self.deposit_amount = prod.deposit_amount
            self.insurance_total = prod.insurance_per_day * (self.rental_days or 1)
            self.cleaning_fee = prod.cleaning_fee
            self.damage_waiver_total = prod.damage_waiver_per_day * (self.rental_days or 1)
            if self.partner_id.rental_tier_id:
                self.discount_pct = self.partner_id.rental_tier_id.discount_pct

    # ── Availability check ────────────────────────────────────────────────────

    def _check_availability(self):
        self.ensure_one()
        if not self.rental_product_id.is_available(
            self.pickup_date, self.expected_return_date, exclude_order_id=self.id
        ):
            raise ValidationError(
                f"'{self.rental_product_id.name}' is not available for the selected dates. "
                "Please choose different dates or a different product."
            )

    # ── State transitions ─────────────────────────────────────────────────────

    def action_reserve(self):
        for order in self:
            order._check_availability()
            order.write({"state": "reserved"})

    def action_sign(self):
        """Record contract signature — required before confirming the rental."""
        for order in self:
            if order.is_signed:
                raise UserError("This rental contract is already signed.")
            order.write(
                {
                    "is_signed": True,
                    "signed_by_id": self.env.user.id,
                    "signed_date": fields.Datetime.now(),
                }
            )
            order.message_post(
                body=(
                    f"<b>Contract Signed</b><br/>"
                    f"Signed by <b>{self.env.user.name}</b> on behalf of "
                    f"{order.partner_id.name}.<br/>"
                    f"Rental: {order.rental_product_id.name} | "
                    f"{order.pickup_date.strftime('%d %b %Y') if order.pickup_date else '?'}"
                    f" → "
                    f"{order.expected_return_date.strftime('%d %b %Y') if order.expected_return_date else '?'}"
                    f"<br/>Total: €{order.final_amount:.2f}"
                ),
                subtype_id=self.env.ref("mail.mt_comment").id,
            )

    def action_confirm(self):
        for order in self:
            order._check_availability()
            if not order.is_signed:
                raise UserError(
                    "The rental contract must be signed before confirming. "
                    "Use the 'Sign Contract' button."
                )
            if not order.deposit_paid and order.deposit_amount:
                raise UserError("Please record the deposit payment before confirming the rental.")
            order.write({"state": "confirmed"})

    def action_pickup(self):
        for order in self:
            if order.state not in ("confirmed", "reserved"):
                raise UserError("Only confirmed or reserved rentals can be picked up.")
            # Verification gate — enforced when a verification record is attached
            if order.verification_id and order.verification_id.status != "verified":
                raise UserError(
                    f"Customer verification for {order.partner_id.name} is not complete "
                    f"(status: {order.verification_id.status}). "
                    "Please verify the customer before recording pickup."
                )
            order._deduct_stock()
            order.write({"state": "picked_up"})

    def action_activate(self):
        self.write({"state": "active"})

    def action_return(self):
        for order in self:
            order.write(
                {
                    "state": "returned",
                    "actual_return_date": fields.Datetime.now(),
                }
            )
            order._return_stock()

    def action_complete_inspection(self):
        """Complete inspection → move to invoiced state."""
        self.write({"state": "invoiced"})

    def action_close(self):
        for order in self:
            order.write({"state": "closed"})
            order._update_partner_annual_spend()

    def action_cancel(self):
        for order in self:
            if order.state in ("picked_up", "active"):
                raise UserError("Cannot cancel an active rental. Complete return first.")
            order.write({"state": "cancelled"})

    def action_record_deposit_paid(self):
        self.write({"deposit_paid": True})

    def action_release_deposit(self):
        """Return the deposit to the customer (full release)."""
        self.write({"deposit_returned": True, "deposit_deducted": 0.0})

    def action_deduct_deposit(self, amount: float = None):
        """Deduct part or all of the deposit for damages."""
        for order in self:
            deduct = amount if amount is not None else order.deposit_amount
            order.write(
                {"deposit_deducted": min(deduct, order.deposit_amount), "deposit_returned": False}
            )

    def action_approve_discount(self):
        """Approve a discount — posts an audit chatter message."""
        for order in self:
            order.write(
                {
                    "discount_approved": True,
                    "discount_approver_id": self.env.user.id,
                }
            )
            discount_type_label = (
                dict(self._fields["discount_type"].selection).get(order.discount_type, "—")
                if order.discount_type
                else "—"
            )
            order.message_post(
                body=(
                    f"<b>Discount Approved</b><br/>"
                    f"Approved by: <b>{self.env.user.name}</b><br/>"
                    f"Type: {discount_type_label}<br/>"
                    f"Discount: {order.discount_pct:.1f}%<br/>"
                    f"Reason: {order.discount_reason or '—'}<br/>"
                    f"Order Total: €{order.final_amount:.2f}"
                ),
                subtype_id=self.env.ref("mail.mt_note").id,
            )

    # ── Stock operations ──────────────────────────────────────────────────────

    def _deduct_stock(self):
        """Deduct 1 unit from stock when rental is picked up."""
        self.ensure_one()
        product = self.rental_product_id.product_id
        if not product or not getattr(product, "is_storable", False):
            return
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse:
            _logger.warning("Rental %s: no warehouse found — skipping stock deduction.", self.name)
            return
        location = warehouse.lot_stock_id
        self.env["stock.quant"]._update_available_quantity(product, location, -1.0)
        _logger.info(
            "Rental pickup %s: deducted 1 × %s from %s.",
            self.name,
            product.display_name,
            location.complete_name,
        )

    def _return_stock(self):
        """Return 1 unit to stock when rental is returned."""
        self.ensure_one()
        product = self.rental_product_id.product_id
        if not product or not getattr(product, "is_storable", False):
            return
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse:
            _logger.warning("Rental %s: no warehouse found — skipping stock return.", self.name)
            return
        location = warehouse.lot_stock_id
        self.env["stock.quant"]._update_available_quantity(product, location, 1.0)
        _logger.info(
            "Rental return %s: returned 1 × %s to %s.",
            self.name,
            product.display_name,
            location.complete_name,
        )

    # ── Invoice creation ──────────────────────────────────────────────────────

    def action_create_invoice(self):
        """Create the final invoice for this rental."""
        self.ensure_one()
        if self.invoice_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": self.invoice_id.id,
                "view_mode": "form",
            }

        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_id.id,
                "ref": self.name,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.rental_product_id.product_id.id,
                            "name": f"Rental: {self.rental_product_id.name} ({self.rental_days} days)",
                            "quantity": 1,
                            "price_unit": self.final_amount,
                        },
                    )
                ],
            }
        )
        self.write({"invoice_id": invoice.id, "state": "invoiced"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
        }

    # ── Return reminder ───────────────────────────────────────────────────────

    def action_send_return_reminder(self):
        """Send a return-due reminder to the customer."""
        for order in self:
            if not order.partner_id:
                continue
            order.message_post(
                body=(
                    f"<b>Return Reminder:</b> Your rental <b>{order.rental_product_id.name}</b> "
                    f"is due for return on "
                    f"{order.expected_return_date.strftime('%d %b %Y %H:%M') if order.expected_return_date else 'TBD'}. "
                    f"Please arrange timely return to avoid late fees."
                ),
                subtype_id=self.env.ref("mail.mt_comment").id,
                partner_ids=order.partner_id.ids,
            )
            order.message_post(
                body="Return reminder sent to customer.",
                subtype_id=self.env.ref("mail.mt_note").id,
            )

    @api.model
    def cron_send_overdue_reminders(self):
        """Cron: send return reminders for rentals overdue or due within 24 h."""
        from datetime import timedelta

        now = fields.Datetime.now()
        due_soon = now + timedelta(hours=24)
        orders = self.search(
            [
                ("state", "in", ("picked_up", "active")),
                ("expected_return_date", "<=", due_soon),
            ]
        )
        orders.action_send_return_reminder()

    # ── Recurring billing ─────────────────────────────────────────────────────

    @api.model
    def cron_generate_recurring_billing(self):
        """Cron: generate periodic invoices for active recurring rentals."""
        from datetime import date, timedelta

        today = date.today()
        orders = self.search(
            [
                ("is_recurring", "=", True),
                ("state", "in", ("picked_up", "active")),
                ("recurring_interval", "!=", False),
            ]
        )
        for order in orders:
            if order.last_invoice_date:
                if order.recurring_interval == "weekly":
                    next_due = order.last_invoice_date + timedelta(weeks=1)
                else:
                    from dateutil.relativedelta import relativedelta

                    next_due = order.last_invoice_date + relativedelta(months=1)
                if next_due > today:
                    continue
            self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": order.partner_id.id,
                    "ref": f"{order.name} (recurring)",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": order.rental_product_id.product_id.id,
                                "name": (
                                    f"Recurring Rental: {order.rental_product_id.name} "
                                    f"({order.recurring_interval})"
                                ),
                                "quantity": 1,
                                "price_unit": order.rental_price,
                            },
                        )
                    ],
                }
            )
            order.last_invoice_date = today

    # ── Annual spend update ───────────────────────────────────────────────────

    def _update_partner_annual_spend(self):
        """Update partner's annual rental spend for tier calculation."""
        self.ensure_one()
        partner = self.partner_id
        from datetime import date

        year_start = date(date.today().year, 1, 1)
        orders = self.search(
            [
                ("partner_id", "=", partner.id),
                ("state", "=", "closed"),
                ("pickup_date", ">=", str(year_start)),
            ]
        )
        total = sum(o.final_amount for o in orders)
        partner.rental_annual_spend = total

    @api.constrains("pickup_date", "expected_return_date")
    def _check_pickup_date_expected_return_date_order(self):
        for rec in self:
            if (
                rec.pickup_date
                and rec.expected_return_date
                and rec.expected_return_date < rec.pickup_date
            ):
                raise ValidationError("Expected return date must be after the pickup date.")
