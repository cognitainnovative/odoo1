"""Versioned Terms & Conditions for quotes."""

from odoo import api, fields, models


class QuoteTermsVersion(models.Model):
    _name = "quote.terms.version"
    _description = "Quote Terms & Conditions Version"
    _order = "version desc"
    _rec_name = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True, help="Stable identifier, e.g. 'standard_nl_v3'")
    version = fields.Integer(required=True, default=1)
    language = fields.Selection(
        [("en", "English"), ("nl", "Dutch"), ("de", "German"), ("fr", "French")],
        default="en",
        required=True,
    )
    content = fields.Html("Terms Content", required=True, translate=True)
    payment_obligation_text = fields.Text(
        "Payment Obligation Wording",
        translate=True,
        help=(
            "Displayed on the signing page above the signature field. "
            "Configurable per terms version. Do not hardcode language-specific phrasing here."
        ),
    )
    is_active = fields.Boolean("Active / Default", default=True)
    effective_date = fields.Date()

    _code_version_uniq = models.Constraint(
        "UNIQUE(code, version, language)",
        "Terms code + version + language must be unique.",
    )

    @api.model
    def get_active_terms(self, language: str = "en") -> "QuoteTermsVersion | None":
        """Return the active terms for the given language, falling back to English."""
        rec = self.search(
            [("is_active", "=", True), ("language", "=", language)],
            order="version desc",
            limit=1,
        )
        if not rec and language != "en":
            rec = self.search(
                [("is_active", "=", True), ("language", "=", "en")],
                order="version desc",
                limit=1,
            )
        return rec or None
