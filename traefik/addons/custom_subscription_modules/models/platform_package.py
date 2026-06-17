from odoo import api, fields, models


class PlatformPackage(models.Model):
    _name = "platform.package"
    _description = "Platform Module Package"
    _order = "sequence, name"
    _rec_name = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    # Comma-separated list of module codes this package grants access to
    module_codes = fields.Char(
        "Module Codes", help="Comma-separated list, e.g. crm,accounting_basic"
    )
    monthly_price = fields.Float("Monthly Price (€)", digits=(10, 2))
    annual_price = fields.Float("Annual Price (€)", digits=(10, 2))
    color = fields.Integer("Kanban Color", default=0)
    active = fields.Boolean(default=True)

    subscription_ids = fields.One2many(
        "platform.subscription", "package_id", string="Subscriptions"
    )
    subscription_count = fields.Integer(compute="_compute_subscription_count")

    _code_uniq = models.Constraint("UNIQUE(code)", "Package code must be unique.")

    @api.depends("subscription_ids")
    def _compute_subscription_count(self):
        counts = self.env["platform.subscription"].read_group(
            [("package_id", "in", self.ids)],
            ["package_id"],
            ["package_id"],
        )
        mapping = {r["package_id"][0]: r["package_id_count"] for r in counts}
        for rec in self:
            rec.subscription_count = mapping.get(rec.id, 0)

    def action_view_subscriptions(self):
        self.ensure_one()
        return {
            "name": f"{self.name} — Subscriptions",
            "type": "ir.actions.act_window",
            "res_model": "platform.subscription",
            "view_mode": "list,form",
            "domain": [("package_id", "=", self.id)],
            "context": {"default_package_id": self.id},
        }
