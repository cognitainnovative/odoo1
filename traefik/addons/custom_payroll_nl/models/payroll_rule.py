"""Versioned Dutch payroll rule parameters — one record per year/version."""

from odoo import api, fields, models


class HrPayrollRuleVersion(models.Model):
    _name = "hr.payroll.rule.version"
    _description = "Dutch Payroll Rule Version"
    _order = "year desc, version desc"
    _rec_name = "display_name"

    year = fields.Integer(required=True)
    version = fields.Integer("Sub-version", default=1)
    is_active = fields.Boolean("Current Rules", default=False)
    notes = fields.Text()

    display_name = fields.Char(compute="_compute_display_name", store=True)

    # ── Loonbelasting brackets (two-bracket simplified model) ─────────────────
    bracket1_max = fields.Float(
        "Bracket 1 Upper Limit (€/yr)",
        default=38_098.0,
        help="Income up to this amount is taxed at bracket1_rate.",
    )
    bracket1_rate = fields.Float("Bracket 1 Rate (%)", default=36.97, help="E.g. 36.97 for 36.97%")
    bracket2_rate = fields.Float(
        "Bracket 2 Rate (%)", default=49.50, help="Rate applied to income above bracket1_max"
    )

    # ── Loonheffingskorting (wage tax credit) ─────────────────────────────────
    lhk_max_amount = fields.Float("Max Loonheffingskorting (€/yr)", default=3_362.0)
    lhk_afbouw_start = fields.Float("LHK Phaseout Start (€/yr)", default=10_000.0)
    lhk_afbouw_end = fields.Float("LHK Phaseout End (€/yr)", default=124_936.0)
    lhk_afbouw_rate = fields.Float(
        "LHK Phaseout Rate (% per €)",
        default=2.06,
        help="Phaseout rate as % per 1 € above afbouw_start. E.g. 2.06 = 2.06% per €.",
    )

    # ── Employer contributions ────────────────────────────────────────────────
    awf_employer_pct = fields.Float("AWF/WW Employer (%)", default=2.74)
    zvw_employer_pct = fields.Float("ZVW Employer (%)", default=6.57)

    # ── Holiday allowance default ─────────────────────────────────────────────
    vakantiegeld_pct = fields.Float("Default Holiday Allowance (%)", default=8.0)

    # ── Bijtelling auto (company car) ─────────────────────────────────────────
    bijtelling_ev_pct = fields.Float("Bijtelling EV (%)", default=16.0)
    bijtelling_standard_pct = fields.Float("Bijtelling Standard (%)", default=22.0)

    # ── Reiskostenvergoeding ──────────────────────────────────────────────────
    max_km_vergoeding = fields.Float("Max Travel Allowance (€/km)", default=0.23)

    _year_version_uniq = models.Constraint(
        "UNIQUE(year, version)", "Year + version must be unique."
    )

    @api.depends("year", "version")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"NL Payroll Rules {rec.year} v{rec.version}"

    @api.model
    def get_active_rules(self) -> "HrPayrollRuleVersion | None":
        rec = self.search([("is_active", "=", True)], order="year desc", limit=1)
        if not rec:
            rec = self.search([], order="year desc", limit=1)
        return rec or None

    def activate(self):
        """Set this version as active, deactivate others."""
        self.search([("is_active", "=", True)]).write({"is_active": False})
        self.is_active = True
