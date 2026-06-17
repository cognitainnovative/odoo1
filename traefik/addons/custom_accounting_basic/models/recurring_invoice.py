"""Recurring invoice templates — auto-generate outgoing invoices on schedule."""

import logging

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_INTERVAL_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


class RecurringInvoiceTemplate(models.Model):
    _name = "recurring.invoice.template"
    _description = "Recurring Invoice Template"
    _inherit = ["mail.thread"]
    _order = "next_date"

    name = fields.Char("Template Name", required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one("res.partner", "Customer", required=True, tracking=True)
    journal_id = fields.Many2one(
        "account.journal",
        "Journal",
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    interval_type = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
        ],
        string="Recurrence",
        required=True,
        default="monthly",
        tracking=True,
    )
    next_date = fields.Date("Next Invoice Date", required=True, tracking=True)
    last_invoice_id = fields.Many2one("account.move", "Last Created Invoice", readonly=True)
    note = fields.Text("Internal Notes")
    line_ids = fields.One2many(
        "recurring.invoice.template.line",
        "template_id",
        "Invoice Lines",
    )

    @api.model
    def _cron_create_recurring(self):
        """Daily cron: create invoices for all due recurring templates."""
        today = fields.Date.today()
        due = self.search([("next_date", "<=", today), ("active", "=", True)])
        for tmpl in due:
            try:
                tmpl.action_create_now()
                self.env["accounting.audit.log"].sudo().log(
                    event_type="recurring_created",
                    res_model="recurring.invoice.template",
                    res_id=tmpl.id,
                    document_ref=tmpl.name,
                    details=f"Recurring invoice auto-created for {tmpl.partner_id.name}",
                )
            except Exception as exc:
                _logger.error("Recurring invoice cron failed for template %s: %s", tmpl.name, exc)

    def action_create_now(self):
        """Create a draft invoice from this template and advance next_date."""
        self.ensure_one()
        journal = self.journal_id or self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.company_id.id)], limit=1
        )
        if not journal:
            raise UserError(f"No sales journal found for company {self.company_id.name}.")

        lines = []
        for tl in self.line_ids:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": tl.name,
                        "quantity": tl.quantity,
                        "price_unit": tl.price_unit,
                        "product_id": tl.product_id.id if tl.product_id else False,
                    },
                )
            )
        if not lines:
            lines = [(0, 0, {"name": self.name, "quantity": 1, "price_unit": 0.0})]

        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_id.id,
                "journal_id": journal.id,
                "company_id": self.company_id.id,
                "narration": self.note or "",
                "invoice_line_ids": lines,
            }
        )

        months = _INTERVAL_MONTHS[self.interval_type]
        next_dt = self.next_date + relativedelta(months=months)
        self.write({"last_invoice_id": move.id, "next_date": next_dt})
        return move


class RecurringInvoiceTemplateLine(models.Model):
    _name = "recurring.invoice.template.line"
    _description = "Recurring Invoice Template Line"
    _order = "sequence, id"

    template_id = fields.Many2one("recurring.invoice.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", "Product")
    name = fields.Char("Description", required=True)
    quantity = fields.Float("Quantity", default=1.0)
    price_unit = fields.Float("Unit Price", digits=(16, 2))
