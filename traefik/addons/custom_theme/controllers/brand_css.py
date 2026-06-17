import base64

from odoo import http
from odoo.http import request


def _sanitize_css(css: str) -> str:
    if not css:
        return ""
    lowered = css.lower()
    if "</style" in lowered or "<script" in lowered:
        css = css.replace("<", "\\3C ")
    return css


def _lighten(hex_color: str, amt: int = 30) -> str:
    """Crude lightening for hover states; falls back to the input on bad data."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        r, g, b = (min(255, c + amt) for c in (r, g, b))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


class BrandCssController(http.Controller):
    @http.route("/web/platform/brand.css", type="http", auth="public")
    def brand_css(self, **kwargs):
        company = request.env.company.sudo()
        primary = company.brand_primary_color or "#1E40AF"
        secondary = company.brand_secondary_color or "#64748B"
        accent = company.brand_accent_color or "#0284C7"
        bg = company.brand_bg_color or "#F8FAFC"
        font_map = {
            "inter": "'Inter', sans-serif",
            "roboto": "'Roboto', sans-serif",
            "open_sans": "'Open Sans', sans-serif",
            "system": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        }
        font = font_map.get(company.brand_font_family or "inter", font_map["inter"])
        custom = _sanitize_css(company.brand_custom_css or "")

        # This :root is the SINGLE authoritative source of the brand variables.
        # The SCSS bundle no longer defines :root, so these are never clobbered.
        css = f""":root {{
  --plt-primary: {primary};
  --plt-primary-light: {_lighten(primary)};
  --plt-secondary: {secondary};
  --plt-accent: {accent};
  --plt-bg: {bg};
  --plt-font: {font};
}}
{custom}
"""
        return request.make_response(
            css,
            headers=[
                ("Content-Type", "text/css; charset=utf-8"),
                # Dynamic per-company CSS that changes whenever an admin edits
                # the brand colors — must NOT be cached, or edits won't show
                # until the cache expires.
                ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ],
        )

    @http.route("/web/platform/favicon", type="http", auth="public")
    def brand_favicon(self, **kwargs):
        """Serve the company's configured brand favicon. Falls back to Odoo's
        default favicon if none is set."""
        company = request.env.company.sudo()
        data = company.brand_favicon
        if data:
            image = base64.b64decode(data)
            return request.make_response(
                image,
                headers=[
                    ("Content-Type", "image/x-icon"),
                    ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
                ],
            )
        # No brand favicon set — redirect to Odoo's stock favicon.
        return request.redirect("/web/static/img/favicon.ico", code=302)
