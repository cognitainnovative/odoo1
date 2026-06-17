"""Portal controller for the quote signing workflow."""

import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class QuoteSigningPortal(http.Controller):

    @http.route("/quote/<string:token>", type="http", auth="public", website=True)
    def view_quote(self, token, **kwargs):
        """Render the quote for the customer to review."""
        order = self._get_order_by_token(token)
        if not order:
            return request.not_found()

        # Mark as viewed
        order.sudo().action_mark_viewed()

        terms = order.sudo().terms_version_id
        payment_text = (
            order.sudo().payment_obligation_text
            or (terms.payment_obligation_text if terms else "")
            or (
                "By signing, I confirm that I have read, understood, and accepted the "
                "above quotation and agree to pay the stated amount according to the "
                "agreed payment terms."
            )
        )

        return request.render(
            "custom_quote_signing.portal_quote_view",
            {
                "order": order.sudo(),
                "terms": terms,
                "payment_obligation_text": payment_text,
                "token": token,
            },
        )

    @http.route(
        "/quote/<string:token>/sign",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        csrf=True,
    )
    def sign_quote(self, token, **post):
        """Process the signing form submission."""
        order = self._get_order_by_token(token)
        if not order:
            return request.not_found()

        signer_name = (post.get("signer_name") or "").strip()
        signer_email = (post.get("signer_email") or "").strip()
        signature_data = post.get("signature_data") or ""
        signature_type = post.get("signature_type") or "drawn"
        terms_accepted = post.get("terms_accepted") == "1"
        payment_accepted = post.get("payment_accepted") == "1"

        # Require a non-trivially-empty signature (base64 PNG must have real content)
        if not signature_data or len(signature_data) < 60:
            return request.render(
                "custom_quote_signing.portal_quote_view",
                {
                    "order": order.sudo(),
                    "terms": order.sudo().terms_version_id,
                    "token": token,
                    "error": "Please draw or type your signature before submitting.",
                    "payment_obligation_text": order.sudo().payment_obligation_text or "",
                },
            )

        if not signer_name or not signer_email:
            return request.render(
                "custom_quote_signing.portal_quote_view",
                {
                    "order": order.sudo(),
                    "terms": order.sudo().terms_version_id,
                    "token": token,
                    "error": "Please provide your full name and email address.",
                    "payment_obligation_text": order.sudo().payment_obligation_text or "",
                },
            )

        if not terms_accepted or not payment_accepted:
            return request.render(
                "custom_quote_signing.portal_quote_view",
                {
                    "order": order.sudo(),
                    "terms": order.sudo().terms_version_id,
                    "token": token,
                    "error": (
                        "You must accept the terms and conditions "
                        "and acknowledge the payment obligation."
                    ),
                    "payment_obligation_text": order.sudo().payment_obligation_text or "",
                },
            )

        ip_address = request.httprequest.remote_addr or ""
        user_agent = request.httprequest.user_agent.string if request.httprequest.user_agent else ""

        events = [
            {
                "event": "page_loaded",
                "ts": str(fields.Datetime.now()),
                "ip": ip_address,
            },
            {
                "event": "signed",
                "ts": str(fields.Datetime.now()),
                "signer_name": signer_name,
                "signer_email": signer_email,
            },
        ]

        try:
            signing = order.sudo().process_signing(
                signer_name=signer_name,
                signer_email=signer_email,
                signature_data=signature_data,
                signature_type=signature_type,
                ip_address=ip_address,
                user_agent=user_agent,
                terms_accepted=terms_accepted,
                payment_accepted=payment_accepted,
                events=events,
            )
            return request.render(
                "custom_quote_signing.portal_quote_signed",
                {
                    "order": order.sudo(),
                    "signing": signing,
                    "signer_name": signer_name,
                },
            )
        except Exception as exc:
            _logger.error("Signing failed for token %s: %s", token, exc)
            return request.render(
                "custom_quote_signing.portal_quote_view",
                {
                    "order": order.sudo(),
                    "terms": order.sudo().terms_version_id,
                    "token": token,
                    "error": f"Signing failed: {exc}",
                    "payment_obligation_text": order.sudo().payment_obligation_text or "",
                },
            )

    @http.route(
        "/quote/<string:token>/accept",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        csrf=False,
    )
    def accept_quote(self, token, **kwargs):
        """AJAX endpoint: set state to accepted_pending when customer ticks both checkboxes."""
        order = self._get_order_by_token(token)
        if not order:
            return request.make_response(
                json.dumps({"error": "not_found"}),
                headers=[("Content-Type", "application/json")],
            )
        order.sudo().action_set_accepted_pending()
        return request.make_response(
            json.dumps({"ok": True, "state": order.sudo().signing_state}),
            headers=[("Content-Type", "application/json")],
        )

    @staticmethod
    def _get_order_by_token(token: str):
        """Fetch the sale.order matching the token, or None."""
        if not token:
            return None
        order = request.env["sale.order"].sudo().search([("signing_token", "=", token)], limit=1)
        return order or None
