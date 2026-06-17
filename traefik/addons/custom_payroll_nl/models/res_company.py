"""Extend res.company with Dutch payroll settings."""

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    loonheffingsnummer = fields.Char(
        "Loonheffingsnummer (Payroll Tax Number)",
        help="Your company's Dutch payroll tax registration number (loonheffingsnummer).",
    )
    payroll_period_type = fields.Selection(
        [("monthly", "Monthly"), ("4week", "4-Weekly")],
        string="Default Payroll Period",
        default="monthly",
    )
    payroll_kvk = fields.Char("KVK Number")
    payroll_legal_disclaimer = fields.Text(
        "Payroll Legal Disclaimer",
        default=(
            "⚠️  LEGAL NOTICE: This payroll is prepared for internal use and export only. "
            "Direct loonaangifte (wage tax filing) with the Belastingdienst requires a "
            "certified submission route. Please consult a certified payroll provider or "
            "accountant for official filing. This module generates the data and "
            "calculations but does NOT submit to the Belastingdienst."
        ),
    )
