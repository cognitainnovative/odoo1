from odoo.tests.common import HttpCase, TransactionCase, tagged


class TestCustomTheme(TransactionCase):
    """Tests for custom_theme brand fields and native-field mirroring."""

    def test_brand_fields_exist(self):
        """res.company has all brand fields."""
        company = self.env.company
        for fname in (
            "brand_logo",
            "brand_favicon",
            "brand_primary_color",
            "brand_secondary_color",
            "brand_accent_color",
            "brand_bg_color",
            "brand_font_family",
            "brand_portal_footer",
            "brand_pdf_header_text",
            "brand_custom_css",
        ):
            self.assertIn(fname, company._fields, f"Missing brand field: {fname}")

    def test_write_brand_color(self):
        """Brand color can be written to and read back."""
        company = self.env.company
        original = company.brand_primary_color
        company.brand_primary_color = "#123456"
        self.assertEqual(company.brand_primary_color, "#123456")
        company.brand_primary_color = original

    def test_brand_logo_mirrors_to_native_logo(self):
        """Setting brand_logo applies it as the company logo (navbar/PDF source)."""
        company = self.env.company
        fake_png = (
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            b"2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        company.write({"brand_logo": fake_png})
        self.assertEqual(
            company.logo, fake_png, "brand_logo must mirror into native res.company.logo"
        )

    def test_brand_favicon_stored(self):
        """brand_favicon is stored on the company (served via /web/platform/favicon)."""
        company = self.env.company
        fake_ico = (
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            b"2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        company.write({"brand_favicon": fake_ico})
        self.assertTrue(company.brand_favicon, "brand_favicon must persist on the company.")

    def test_pdf_header_mirrors_to_report_header(self):
        """brand_pdf_header_text feeds the report header rendered on PDFs."""
        company = self.env.company
        company.write({"brand_pdf_header_text": "Quality first — Cognita"})
        self.assertIn(
            "Quality first",
            str(company.report_header or ""),
            "brand_pdf_header_text must mirror into report_header",
        )


@tagged("post_install", "-at_install")
class TestBrandingApplied(HttpCase):
    """Acceptance gate: branding is visibly applied (M1)."""

    def test_brand_css_served_with_company_colors(self):
        """/web/platform/brand.css serves the company's configured colors."""
        self.env.company.write({"brand_primary_color": "#ABCDEF"})
        self.authenticate("admin", "admin")
        response = self.url_open("/web/platform/brand.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers.get("Content-Type", ""))
        self.assertIn("#ABCDEF", response.text, "Configured brand color must appear in served CSS.")
        self.assertIn("--plt-primary", response.text)

    def test_brand_css_linked_in_webclient(self):
        """The brand.css link is injected into the page head (web.layout)."""
        self.authenticate("admin", "admin")
        response = self.url_open("/odoo")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/web/platform/brand.css",
            response.text,
            "brand.css link must be present in the web client page.",
        )

    def test_favicon_route_serves_brand_favicon(self):
        """/web/platform/favicon returns the configured favicon bytes."""
        fake_ico = (
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            b"2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        self.env.company.write({"brand_favicon": fake_ico})
        self.authenticate("admin", "admin")
        response = self.url_open("/web/platform/favicon")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.headers.get("Content-Type", ""))
