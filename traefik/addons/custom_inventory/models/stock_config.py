"""Platform inventory configuration + auto stock deduction settings."""

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_deduct_on = fields.Selection(
        [
            ("sale_confirm", "On Sale Order Confirm"),
            ("invoice_confirm", "On Invoice Confirm"),
            ("delivery", "On Delivery (Odoo default)"),
        ],
        string="Auto Stock Deduction",
        default="delivery",
        config_parameter="custom_inventory.stock_deduct_on",
        help=(
            "When to automatically trigger stock deduction. "
            "'Delivery' uses Odoo's standard picking workflow. "
            "'Sale Order Confirm' or 'Invoice Confirm' immediately deducts "
            "stock when that document is confirmed."
        ),
    )
    low_stock_alert_email = fields.Char(
        "Low-Stock Alert Email",
        config_parameter="custom_inventory.low_stock_alert_email",
        help="Send low-stock alerts to this address. Leave blank to disable.",
    )
    low_stock_alert_days = fields.Integer(
        "Low-Stock Alert Check (days)",
        default=7,
        config_parameter="custom_inventory.low_stock_alert_days",
    )
