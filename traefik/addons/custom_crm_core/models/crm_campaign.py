"""CRM Campaign model — track lead sources and marketing campaigns."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrmCampaign(models.Model):
    _name = "crm.campaign"
    _description = "CRM Campaign"
    _inherit = ["mail.thread"]
    _order = "start_date desc, name"
    _rec_name = "name"

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda s: s.env.company, index=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("paused", "Paused"), ("done", "Done")],
        default="draft",
        tracking=True,
    )
    channel = fields.Selection(
        [
            ("email", "Email"),
            ("social", "Social Media"),
            ("paid_search", "Paid Search"),
            ("organic_search", "Organic Search"),
            ("referral", "Referral"),
            ("event", "Event"),
            ("cold_call", "Cold Call"),
            ("partner", "Partner"),
            ("other", "Other"),
        ],
        default="other",
    )
    start_date = fields.Date()
    end_date = fields.Date()
    budget = fields.Float("Budget (€)", digits=(10, 2))
    target_leads = fields.Integer("Target Leads")
    description = fields.Text()
    utm_source = fields.Char("UTM Source")
    utm_medium = fields.Char("UTM Medium")
    utm_campaign = fields.Char("UTM Campaign Name")

    lead_ids = fields.One2many("crm.lead", "platform_campaign_id", "Leads")
    lead_count = fields.Integer(compute="_compute_lead_stats")
    won_count = fields.Integer(compute="_compute_lead_stats")
    total_revenue = fields.Float(compute="_compute_lead_stats", digits=(12, 2))

    def _compute_lead_stats(self):
        for rec in self:
            leads = rec.lead_ids
            rec.lead_count = len(leads)
            won = leads.filtered(lambda lead: lead.probability >= 100)
            rec.won_count = len(won)
            rec.total_revenue = sum(won.mapped("expected_revenue"))

    def action_activate(self):
        self.write({"state": "active"})

    def action_done(self):
        self.write({"state": "done"})

    def action_view_leads(self):
        self.ensure_one()
        return {
            "name": f"{self.name} — Leads",
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "kanban,list,form",
            "domain": [("platform_campaign_id", "=", self.id)],
            "context": {"default_platform_campaign_id": self.id},
        }

    @api.constrains("start_date", "end_date")
    def _check_start_date_end_date_order(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError("Campaign end date must be after the start date.")

    @api.constrains("start_date", "end_date")
    def _check_start_date_end_date_order(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError("Campaign end date must be after the start date.")
