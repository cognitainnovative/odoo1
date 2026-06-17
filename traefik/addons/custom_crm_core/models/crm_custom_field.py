"""Per-company custom field definitions for crm.lead (EAV pattern)."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrmCustomField(models.Model):
    _name = "crm.custom.field"
    _description = "CRM Custom Field Definition"
    _order = "company_id, sequence, name"

    name = fields.Char("Field Label", required=True)
    field_key = fields.Char(
        "Key",
        required=True,
        help="Alphanumeric slug used as identifier (letters, digits, underscores only).",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda s: s.env.company, index=True
    )
    field_type = fields.Selection(
        [
            ("char", "Text"),
            ("integer", "Integer"),
            ("float", "Decimal"),
            ("boolean", "Yes / No"),
            ("date", "Date"),
        ],
        string="Type",
        default="char",
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _unique_key_company = models.Constraint(
        "UNIQUE(field_key, company_id)",
        "Field key must be unique per company.",
    )

    @api.constrains("field_key")
    def _check_field_key(self):
        for rec in self:
            if not rec.field_key.replace("_", "").isalnum():
                raise ValidationError(
                    "Field key may only contain letters, digits, and underscores."
                )


class CrmCustomFieldValue(models.Model):
    _name = "crm.custom.field.value"
    _description = "CRM Custom Field Value"
    _order = "field_id"

    lead_id = fields.Many2one("crm.lead", required=True, ondelete="cascade", index=True)
    field_id = fields.Many2one("crm.custom.field", required=True, ondelete="cascade", index=True)
    field_label = fields.Char(related="field_id.name", store=True)
    field_type = fields.Selection(related="field_id.field_type", store=True)
    company_id = fields.Many2one(related="field_id.company_id", store=True, index=True)
    # All values stored as char; callers cast as needed using field_type
    value_char = fields.Char("Value")

    _unique_lead_field = models.Constraint(
        "UNIQUE(lead_id, field_id)",
        "A lead can only have one value per custom field.",
    )
