"""Simplified fixed asset tracking with straight-line depreciation."""

from odoo import api, fields, models


class AccountFixedAsset(models.Model):
    _name = "account.fixed.asset"
    _description = "Fixed Asset"
    _inherit = ["mail.thread"]
    _order = "acquisition_date desc, name"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    category = fields.Selection(
        [
            ("building", "Building"),
            ("machinery", "Machinery / Equipment"),
            ("vehicle", "Vehicle"),
            ("furniture", "Furniture & Fittings"),
            ("computer", "Computer / IT Equipment"),
            ("intangible", "Intangible Asset"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("disposed", "Disposed")],
        default="draft",
        tracking=True,
    )

    # Acquisition
    acquisition_date = fields.Date("Acquisition Date", required=True)
    acquisition_value = fields.Float("Acquisition Value (€)", digits=(14, 2), required=True)
    residual_value = fields.Float("Residual Value (€)", digits=(14, 2), default=0.0)

    # Depreciation
    depreciation_method = fields.Selection(
        [("straight_line", "Straight Line"), ("none", "No Depreciation")],
        default="straight_line",
    )
    useful_life_years = fields.Integer("Useful Life (years)", default=5)
    annual_depreciation = fields.Float(
        "Annual Depreciation (€)", compute="_compute_depreciation", store=True, digits=(14, 2)
    )
    accumulated_depreciation = fields.Float(
        "Accumulated Depreciation (€)", digits=(14, 2), readonly=True
    )
    net_book_value = fields.Float(
        "Net Book Value (€)", compute="_compute_nbv", store=True, digits=(14, 2)
    )

    # Disposal
    disposal_date = fields.Date(readonly=True)
    disposal_value = fields.Float("Disposal Value (€)", digits=(14, 2))
    gain_loss = fields.Float(
        "Gain / Loss on Disposal (€)", compute="_compute_gain_loss", store=True
    )

    # Account links
    asset_account_id = fields.Many2one(
        "account.account",
        "Asset Account",
        domain="[('account_type', 'in', ('asset_fixed', 'asset_non_current'))]",
    )
    depreciation_account_id = fields.Many2one(
        "account.account",
        "Depreciation Expense Account",
        domain="[('account_type', '=', 'expense')]",
    )
    accumulated_dep_account_id = fields.Many2one(
        "account.account",
        "Accumulated Dep. Account",
    )

    depreciation_line_ids = fields.One2many(
        "account.fixed.asset.line", "asset_id", "Depreciation Schedule"
    )

    @api.depends("acquisition_value", "residual_value", "useful_life_years", "depreciation_method")
    def _compute_depreciation(self):
        for asset in self:
            if asset.depreciation_method == "straight_line" and asset.useful_life_years:
                asset.annual_depreciation = (
                    asset.acquisition_value - asset.residual_value
                ) / asset.useful_life_years
            else:
                asset.annual_depreciation = 0.0

    @api.depends("acquisition_value", "accumulated_depreciation")
    def _compute_nbv(self):
        for asset in self:
            asset.net_book_value = asset.acquisition_value - asset.accumulated_depreciation

    @api.depends("net_book_value", "disposal_value")
    def _compute_gain_loss(self):
        for asset in self:
            if asset.state == "disposed":
                asset.gain_loss = asset.disposal_value - asset.net_book_value
            else:
                asset.gain_loss = 0.0

    def action_start(self):
        self.write({"state": "active"})

    def action_dispose(self, disposal_value: float = 0.0):
        self.write(
            {
                "state": "disposed",
                "disposal_date": fields.Date.today(),
                "disposal_value": disposal_value,
            }
        )

    def generate_depreciation_schedule(self):
        """Generate the full depreciation schedule for this asset."""
        self.ensure_one()
        if self.depreciation_method != "straight_line":
            return

        # Remove existing lines
        self.depreciation_line_ids.unlink()

        from dateutil.relativedelta import relativedelta

        start = self.acquisition_date
        annual = self.annual_depreciation
        accumulated = 0.0

        for year in range(self.useful_life_years):
            period_date = start + relativedelta(years=year + 1)
            if year == self.useful_life_years - 1:
                # Last year: use remaining value
                dep = self.acquisition_value - self.residual_value - accumulated
            else:
                dep = annual
            accumulated += dep
            self.env["account.fixed.asset.line"].create(
                {
                    "asset_id": self.id,
                    "date": period_date,
                    "depreciation_amount": round(dep, 2),
                    "accumulated_depreciation": round(accumulated, 2),
                    "net_book_value": round(self.acquisition_value - accumulated, 2),
                }
            )


class AccountFixedAssetLine(models.Model):
    _name = "account.fixed.asset.line"
    _description = "Asset Depreciation Line"
    _order = "date"

    asset_id = fields.Many2one("account.fixed.asset", required=True, ondelete="cascade")
    date = fields.Date(required=True)
    depreciation_amount = fields.Float("Depreciation (€)", digits=(14, 2))
    accumulated_depreciation = fields.Float("Accumulated (€)", digits=(14, 2))
    net_book_value = fields.Float("NBV (€)", digits=(14, 2))
    posted = fields.Boolean("Posted", default=False, readonly=True)
    move_id = fields.Many2one("account.move", "Journal Entry", readonly=True)
