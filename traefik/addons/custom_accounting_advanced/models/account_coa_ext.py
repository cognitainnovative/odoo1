"""Chart of accounts extension — adds platform-specific fields to account.account."""

from odoo import fields, models


class AccountAccountPlatformExt(models.Model):
    _inherit = "account.account"

    cost_centre_default_id = fields.Many2one(
        "account.cost.centre",
        "Default Cost Centre",
        help="Default cost centre for journal lines using this account.",
    )
    is_reconcilable_platform = fields.Boolean(
        "Platform Reconcilable",
        help="Mark accounts that should be reconciled in the platform closing workflow.",
    )
    platform_account_group = fields.Selection(
        [
            ("operating", "Operating"),
            ("investing", "Investing"),
            ("financing", "Financing"),
            ("neutral", "Neutral / Other"),
        ],
        "Cash Flow Category",
        help="Cash flow statement categorisation for management reports.",
    )
    external_ref = fields.Char(
        "External Reference",
        help="Reference code for integration with external accounting systems.",
    )
    account_notes = fields.Text("Account Notes")
