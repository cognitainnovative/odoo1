"""Extend sale.order with signing workflow, portal token, and lifecycle states."""

import secrets

from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ── Signing lifecycle ─────────────────────────────────────────────────────
    signing_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("viewed", "Viewed by Customer"),
            ("accepted_pending", "Accepted — Pending Signature"),
            ("signed", "Signed"),
            ("confirmed", "Confirmed"),
            ("invoiced", "Invoiced"),
            ("cancelled", "Cancelled"),
            ("expired", "Expired"),
        ],
        string="Signing Status",
        default="draft",
        tracking=True,
        index=True,
    )
    signing_token = fields.Char("Signing Token", copy=False, index=True)
    signing_id = fields.Many2one("quote.signing", "Signing Record", readonly=True)
    signed_at = fields.Datetime(related="signing_id.signed_at", string="Signed At", store=True)
    signer_name = fields.Char(related="signing_id.signer_name", string="Signer Name", store=True)

    # ── Portal URL ────────────────────────────────────────────────────────────
    portal_signing_url = fields.Char(
        "Portal Signing URL", compute="_compute_portal_signing_url", store=False
    )

    # ── Terms ─────────────────────────────────────────────────────────────────
    terms_version_id = fields.Many2one("quote.terms.version", "Terms Version")
    payment_obligation_text = fields.Text(
        "Payment Obligation Wording",
        help="Shown on the signing page. Defaults to the selected Terms Version's text.",
    )

    # ── Planning ──────────────────────────────────────────────────────────────
    requires_planning = fields.Boolean(
        "Requires Planning on Signing",
        default=True,
        help="If checked, a planning job is auto-created when the quote is confirmed.",
    )
    planning_task_created = fields.Boolean(readonly=True, default=False)

    # ── Expiry ────────────────────────────────────────────────────────────────
    quote_expiry_date = fields.Date("Quote Expiry Date")

    # ── eIDAS / QTSP qualified-signature blocker ──────────────────────────────
    require_qualified_signature = fields.Boolean(
        "Requires Qualified (eIDAS) Signature",
        default=False,
        help=(
            "FLAG: This deal requires an eIDAS qualified electronic signature (QES). "
            "A QES requires a QTSP (Qualified Trust Service Provider) integration "
            "which is NOT included in this platform. "
            "Mark this flag to block standard e-signing and show a blocker message on the portal. "
            "Contact your implementation partner to arrange a certified QTSP connection."
        ),
    )

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends("signing_token")
    def _compute_portal_signing_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        for order in self:
            if order.signing_token:
                order.portal_signing_url = f"{base}/quote/{order.signing_token}"
            else:
                order.portal_signing_url = ""

    # ── Token management ──────────────────────────────────────────────────────

    def _ensure_signing_token(self):
        for order in self:
            if not order.signing_token:
                order.signing_token = secrets.token_urlsafe(32)

    # ── Lifecycle actions ─────────────────────────────────────────────────────

    def action_send_for_signing(self):
        """Generate token, set state to sent, send email to customer."""
        for order in self:
            order._ensure_signing_token()
            if not order.terms_version_id:
                terms = self.env["quote.terms.version"].get_active_terms()
                if terms:
                    order.terms_version_id = terms
            order.signing_state = "sent"
            # Auto-populate payment obligation text from terms
            if order.terms_version_id and not order.payment_obligation_text:
                order.payment_obligation_text = order.terms_version_id.payment_obligation_text or ""
            order._send_signing_email()
        return True

    def action_mark_viewed(self):
        """Called when the customer opens the portal page."""
        for order in self:
            if order.signing_state == "sent":
                order.signing_state = "viewed"

    def action_confirm_signed(self):
        """Confirm a signed quote — triggers deal won + invoice creation path."""
        for order in self:
            if order.signing_state != "signed":
                raise UserError("Only signed quotes can be confirmed.")
            order.signing_state = "confirmed"
            # Mark the linked CRM opportunity as won
            if order.opportunity_id:
                order.opportunity_id.action_set_won()
            # Create planning task if required
            if order.requires_planning and not order.planning_task_created:
                order._create_planning_task()

    def action_expire(self):
        self.write({"signing_state": "expired"})

    def action_cancel_signing(self):
        self.write({"signing_state": "cancelled"})

    def action_reset_to_draft(self):
        for order in self:
            if order.signing_state in ("signed", "confirmed", "invoiced"):
                raise UserError("Cannot reset a signed or confirmed quote to draft.")
            order.signing_state = "draft"

    def action_set_accepted_pending(self):
        """Set state to accepted_pending — called via AJAX when customer ticks both checkboxes."""
        for order in self:
            if order.signing_state in ("sent", "viewed"):
                order.signing_state = "accepted_pending"

    def action_mark_invoiced(self):
        """Mark as fully invoiced — called when all related invoices are confirmed/paid."""
        for order in self:
            if order.signing_state != "confirmed":
                raise UserError("Only confirmed orders can be marked as invoiced.")
            order.signing_state = "invoiced"

    # ── Signing process ───────────────────────────────────────────────────────

    def process_signing(
        self,
        *,
        signer_name: str,
        signer_email: str,
        signature_data: str = "",
        signature_type: str = "drawn",
        ip_address: str = "",
        user_agent: str = "",
        terms_accepted: bool = False,
        payment_accepted: bool = False,
        events: list | None = None,
    ):
        """Called by the portal controller to record the signing."""
        self.ensure_one()

        if self.signing_state not in ("sent", "viewed", "accepted_pending"):
            raise UserError("This quote is not available for signing.")

        # eIDAS/QTSP blocker — enforced server-side, not just hidden in the UI.
        # A qualified electronic signature requires a QTSP integration that is
        # not part of this platform; standard e-signing must be refused.
        if self.require_qualified_signature:
            raise UserError(
                "This quote requires a qualified electronic signature (eIDAS QES) "
                "via a QTSP integration, which is not available. Standard "
                "electronic signing is blocked for this document."
            )

        if not terms_accepted or not payment_accepted:
            raise UserError("You must accept the terms and conditions and the payment obligation.")

        # Generate a PDF for hashing
        pdf_bytes = self._generate_quote_pdf()
        doc_hash = self.env["quote.signing"].compute_document_hash(pdf_bytes)

        signing = self.env["quote.signing"].create_signing_record(
            sale_order=self,
            signer_name=signer_name,
            signer_email=signer_email,
            ip_address=ip_address,
            user_agent=user_agent,
            document_hash=doc_hash,
            signature_data=signature_data,
            signature_type=signature_type,
            terms_accepted=terms_accepted,
            payment_obligation_accepted=payment_accepted,
            terms_version=self.terms_version_id or None,
            events=events or [],
        )

        self.write({"signing_state": "signed", "signing_id": signing.id})

        # Internal notification: posts to chatter, notifies all followers (incl. salesperson)
        self.message_post(
            body=(
                f"<b>Quote signed</b> by {signer_name} ({signer_email}).<br/>"
                f"IP: {ip_address or 'unknown'}&nbsp;·&nbsp;"
                f"Hash: <code>{doc_hash[:20]}…</code>"
            ),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

        # Attach the signed PDF
        self._attach_signed_pdf(signing, pdf_bytes)

        # Send confirmation email to customer
        self._send_signed_confirmation_email(signing)

        return signing

    def _generate_quote_pdf(self) -> bytes:
        """Render the quote report to PDF bytes for hashing.

        If real PDF rendering fails, fall back to a stable JSON representation so
        signing can still proceed and produce a deterministic hash — but log a
        LOUD warning, because a signed record backed by a JSON stub instead of
        the actual quote PDF is a degraded legal-evidence situation that an
        operator must notice and fix (e.g. a broken report template).
        """
        try:
            report = self.env.ref("custom_quote_signing.action_report_signed_quote")
            pdf_content, _ = report._render_qweb_pdf(self.ids)
            return pdf_content
        except Exception as exc:
            import json
            import logging

            logging.getLogger(__name__).error(
                "SIGNED-PDF DEGRADED for %s: real PDF render failed (%s). "
                "Falling back to JSON stub for hashing — the signed document is "
                "NOT a rendered PDF. Fix the report template.",
                self.name,
                exc,
            )
            data = {
                "id": self.id,
                "name": self.name,
                "amount_total": str(self.amount_total),
                "write_date": str(self.write_date),
            }
            return json.dumps(data, sort_keys=True).encode()

    def _attach_signed_pdf(self, signing, pdf_bytes: bytes):
        """Attach the signed PDF to the signing record."""
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": f"Signed Quote {self.name}.pdf",
                    "type": "binary",
                    "datas": __import__("base64").b64encode(pdf_bytes),
                    "res_model": "sale.order",
                    "res_id": self.id,
                    "mimetype": "application/pdf",
                }
            )
        )
        signing.sudo()._write_signed_pdf(attachment)

    def _create_planning_task(self):
        """Create a platform.planning.job linked to this sale order.

        The planning module (custom_planning) is an OPTIONAL companion: quote
        signing must work standalone. If platform.planning.job is not installed,
        skip job creation gracefully (logged) rather than breaking the confirm
        transition. When custom_planning is present, the job is auto-created.
        """
        import logging
        from datetime import timedelta

        if "platform.planning.job" not in self.env:
            logging.getLogger(__name__).info(
                "custom_planning not installed — skipping planning job for %s "
                "(quote confirmed normally).",
                self.name,
            )
            return

        now = fields.Datetime.now()
        self.env["platform.planning.job"].create(
            {
                "name": f"Job: {self.name}",
                "job_type": "installation",
                "sale_order_id": self.id,
                "partner_id": self.partner_id.id,
                "company_id": self.company_id.id,
                "start_datetime": now + timedelta(days=1),
                "end_datetime": now + timedelta(days=1, hours=2),
                "state": "draft",
                "send_customer_confirmation": False,
                "crm_lead_id": self.opportunity_id.id if self.opportunity_id else False,
            }
        )
        self.planning_task_created = True

    def _send_signing_email(self):
        """Send the quote signing request email."""
        template = self.env.ref(
            "custom_quote_signing.email_template_quote_signing", raise_if_not_found=False
        )
        if template and self.partner_id:
            template.send_mail(self.id, force_send=False)

    def _send_signed_confirmation_email(self, signing):
        """Send the signed confirmation email to customer and internal team."""
        template = self.env.ref(
            "custom_quote_signing.email_template_quote_signed", raise_if_not_found=False
        )
        if template:
            template.send_mail(self.id, force_send=False)

    @api.model
    def _cron_expire_quotes(self):
        """Daily cron: expire sent/viewed quotes whose quote_expiry_date has passed."""
        today = fields.Date.today()
        overdue = self.search(
            [
                ("quote_expiry_date", "<", today),
                ("signing_state", "in", ("sent", "viewed", "accepted_pending")),
            ]
        )
        if overdue:
            overdue.write({"signing_state": "expired"})
            import logging

            logging.getLogger(__name__).info("Auto-expired %d overdue quote(s).", len(overdue))


class QuoteSigningPdfPatch(models.Model):
    """Minimal patch: allow writing signed_pdf_attachment_id on quote.signing via sudo."""

    _inherit = "quote.signing"

    def _write_signed_pdf(self, attachment):
        # Bypass immutability guard for this internal use only
        super(models.Model, self).write({"signed_pdf_attachment_id": attachment.id})
