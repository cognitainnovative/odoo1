"""Webhook controller for WhatsApp and social platform callbacks."""

import hashlib
import hmac as hmac_lib
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _verify_meta_signature(provider, req) -> bool:
    """Verify Meta/Facebook HMAC-SHA256 webhook signature.

    Returns True for mock provider or when no app secret is configured (dev/sandbox mode).
    """
    if provider.provider == "mock" or not provider._app_secret_encrypted:
        return True
    try:
        from odoo.addons.custom_whatsapp_social.lib.encryption import decrypt_key

        app_secret = decrypt_key(provider._app_secret_encrypted)
        if not app_secret:
            return True
    except Exception:
        return True

    sig_header = req.httprequest.headers.get("X-Hub-Signature-256", "")
    if not sig_header.startswith("sha256="):
        _logger.warning("Meta webhook signature header missing or malformed")
        return False
    received = sig_header[7:]
    body = req.httprequest.get_data()
    expected = hmac_lib.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac_lib.compare_digest(received, expected)


class WhatsappWebhookController(http.Controller):

    @http.route(
        "/whatsapp/webhook/<int:provider_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def whatsapp_verify(self, provider_id, **kwargs):
        """Meta webhook verification challenge."""
        provider = request.env["whatsapp.provider"].sudo().browse(provider_id)
        hub_mode = kwargs.get("hub.mode")
        hub_token = kwargs.get("hub.verify_token")
        hub_challenge = kwargs.get("hub.challenge", "")

        if (
            hub_mode == "subscribe"
            and provider.webhook_verify_token
            and hub_token == provider.webhook_verify_token
        ):
            return request.make_response(hub_challenge, headers=[("Content-Type", "text/plain")])
        return request.make_response(
            "Forbidden", status=403, headers=[("Content-Type", "text/plain")]
        )

    @http.route(
        "/whatsapp/webhook/<int:provider_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_inbound(self, provider_id, **kwargs):
        """Receive inbound WhatsApp messages."""
        provider = request.env["whatsapp.provider"].sudo().browse(provider_id)
        if not provider.exists():
            return request.make_response(
                "Not Found", status=404, headers=[("Content-Type", "text/plain")]
            )
        if not _verify_meta_signature(provider, request):
            return request.make_response(
                "Forbidden", status=403, headers=[("Content-Type", "text/plain")]
            )
        try:
            payload = json.loads(request.httprequest.data or "{}")
            request.env["whatsapp.message"].sudo().process_inbound_webhook(payload, provider_id)
        except Exception as exc:
            _logger.error("WhatsApp webhook error: %s", exc)
        return request.make_response("OK", headers=[("Content-Type", "text/plain")])

    @http.route(
        "/social/webhook/<int:account_id>", type="http", auth="public", methods=["POST"], csrf=False
    )
    def social_inbound(self, account_id, **kwargs):
        """Receive inbound social messages (Facebook/Instagram/etc.)."""
        try:
            payload = json.loads(request.httprequest.data or "{}")
            account = request.env["social.account"].sudo().browse(account_id)
            if account.exists():
                request.env["social.message"].sudo().create(
                    {
                        "account_id": account.id,
                        "body": payload.get("text", payload.get("message", "")),
                        "author_name": payload.get("from", {}).get("name", "Unknown"),
                        "external_message_id": payload.get("id", ""),
                        "message_type": payload.get("type", "comment"),
                    }
                )
        except Exception as exc:
            _logger.error("Social webhook error: %s", exc)
        return request.make_response("OK", headers=[("Content-Type", "text/plain")])
