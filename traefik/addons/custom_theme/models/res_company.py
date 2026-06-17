from odoo import api, fields, models

# Brand fields that mirror into native res.company fields which Odoo already
# renders everywhere (backend navbar, browser favicon, PDF external layouts).
# Mirroring instead of template-overriding keeps us compatible with all
# report layouts and the standard /web/binary/company_logo route.
# Map brand_* fields onto native res.company fields Odoo already renders.
# NOTE: res.company has `logo` and `report_header`, but NOT `favicon` on this
# build (favicon lives on res.website). _apply_brand_mirror() defensively
# skips any target that isn't a real field on res.company, so this map can
# list optional targets without risking an "Invalid field" write error.
_BRAND_MIRROR = {
    "brand_logo": "logo",  # navbar + PDF logo
    "brand_favicon": "favicon",  # only mirrored if the field exists
    "brand_pdf_header_text": "report_header",  # report layout tagline
}


class ResCompany(models.Model):
    _inherit = "res.company"

    # ── Visual identity ────────────────────────────────────────────────────────
    brand_logo = fields.Binary(
        "Brand Logo",
        attachment=True,
        help="Logo shown in the backend header and on PDFs/emails. "
        "Overrides the standard company logo when set.",
    )
    brand_favicon = fields.Binary(
        "Favicon",
        attachment=True,
        help="Browser tab icon (ICO/PNG, 32×32 recommended).",
    )

    # ── Colors ─────────────────────────────────────────────────────────────────
    brand_primary_color = fields.Char("Brand Primary Color", default="#1E40AF")
    brand_secondary_color = fields.Char("Brand Secondary Color", default="#64748B")
    brand_accent_color = fields.Char("Brand Accent Color", default="#0284C7")
    brand_bg_color = fields.Char("Brand Background Color", default="#F8FAFC")
    brand_font_family = fields.Selection(
        [
            ("inter", "Inter"),
            ("system", "System Default"),
            ("roboto", "Roboto"),
            ("open_sans", "Open Sans"),
        ],
        string="Font Family",
        default="inter",
    )

    # ── Portal / email ─────────────────────────────────────────────────────────
    brand_portal_footer = fields.Html("Portal Footer Text", translate=True)
    brand_email_header_html = fields.Html(
        "Email Header HTML",
        translate=True,
        help="Optional HTML block injected at the top of outgoing transactional emails.",
    )
    brand_email_footer_html = fields.Html(
        "Email Footer HTML",
        translate=True,
        help="Legal notice, unsubscribe text, social links, etc.",
    )
    brand_pdf_header_text = fields.Char(
        "PDF Header Text",
        translate=True,
        help="Short tagline shown on invoice/quote PDFs below the logo. "
        "Mirrored into the company report header.",
    )

    # ── Advanced ───────────────────────────────────────────────────────────────
    brand_custom_css = fields.Text("Custom CSS (Advanced)")

    # ── Mirror brand fields into native company fields ─────────────────────────

    def _apply_brand_mirror(self, vals):
        # Only mirror into native fields that actually exist on res.company on
        # this Odoo build (e.g. `favicon` is not a company field here).
        for brand_field, native_field in _BRAND_MIRROR.items():
            if native_field not in self._fields:
                continue
            if vals.get(brand_field) and native_field not in vals:
                vals[native_field] = vals[brand_field]
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        # Odoo 19 editable-list "New" auto-saves with only field defaults, no name yet.
        # Provide a placeholder so the NOT NULL constraint on res_company.name is satisfied.
        for vals in vals_list:
            if not vals.get("name") and not vals.get("partner_id"):
                vals["name"] = self.env._("New Company")
            self._apply_brand_mirror(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._apply_brand_mirror(vals)
        return super().write(vals)
