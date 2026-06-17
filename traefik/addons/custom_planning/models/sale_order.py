"""Link sale.order to planning jobs — auto-create draft job when a service quote is confirmed."""

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    planning_job_ids = fields.One2many("platform.planning.job", "sale_order_id", "Planning Jobs")
    planning_job_count = fields.Integer(compute="_compute_planning_job_count")

    @api.depends("planning_job_ids")
    def _compute_planning_job_count(self):
        for order in self:
            order.planning_job_count = len(order.planning_job_ids)

    def action_view_planning_jobs(self):
        self.ensure_one()
        return {
            "name": f"{self.name} — Planning Jobs",
            "type": "ir.actions.act_window",
            "res_model": "platform.planning.job",
            "view_mode": "list,kanban,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {
                "default_sale_order_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }

    def action_confirm(self):
        """Confirm the sale order; auto-create a draft planning job if none exists yet."""
        result = super().action_confirm()
        for order in self.filtered(lambda o: o.state == "sale"):
            # Skip if a job was already created (e.g. via quote signing)
            if order.planning_job_ids:
                continue
            # Determine whether this order needs planning:
            #  - explicit requires_planning flag wins if present, else
            #  - auto-create only when the order contains a SERVICE product
            #    (services need execution/scheduling; physical goods don't).
            requires = getattr(order, "requires_planning", None)
            if requires is False:
                continue
            if not requires:
                has_service = any(
                    line.product_id and line.product_id.type == "service"
                    for line in order.order_line
                )
                if not has_service:
                    continue
            now = fields.Datetime.now()
            self.env["platform.planning.job"].create(
                {
                    "name": f"Job: {order.name}",
                    "job_type": "installation",
                    "sale_order_id": order.id,
                    "partner_id": order.partner_id.id,
                    "company_id": order.company_id.id,
                    "start_datetime": now + timedelta(days=1),
                    "end_datetime": now + timedelta(days=1, hours=2),
                    "state": "draft",
                    "send_customer_confirmation": False,
                    "crm_lead_id": (
                        order.opportunity_id.id
                        if hasattr(order, "opportunity_id") and order.opportunity_id
                        else False
                    ),
                }
            )
        return result
