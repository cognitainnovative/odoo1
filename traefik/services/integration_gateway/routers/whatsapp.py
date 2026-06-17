"""WhatsApp Cloud API webhook receiver.

GET  /webhooks/whatsapp/{provider_id}  — Meta verification challenge
POST /webhooks/whatsapp/{provider_id}  — inbound messages + status updates

Verifies X-Hub-Signature-256 before forwarding to Odoo.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from normalizers.whatsapp import normalise_whatsapp
from security.meta import verify_meta_signature

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


@router.get("/{provider_id}", response_class=PlainTextResponse)
async def whatsapp_verify(provider_id: int, request: Request):
    """Return hub.challenge to complete Meta webhook subscription."""
    params = dict(request.query_params)
    hub_mode = params.get("hub.mode")
    hub_challenge = params.get("hub.challenge", "")
    hub_token = params.get("hub.verify_token", "")

    # Forward verification to Odoo so the provider token is checked there
    from odoo_client import get_odoo_client
    try:
        client = get_odoo_client()
        result = await client.call(
            "whatsapp.provider", "verify_webhook_token",
            [provider_id, hub_mode, hub_token],
        )
    except Exception as exc:
        _logger.warning("Odoo verify_webhook_token failed: %s", exc)
        result = hub_mode == "subscribe"

    if result:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{provider_id}")
async def whatsapp_inbound(provider_id: int, request: Request):
    """Verify signature, normalise, forward to Odoo."""
    from config import get_settings
    from odoo_client import get_odoo_client

    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_meta_signature(body, sig, settings.whatsapp_app_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    import json
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    messages = normalise_whatsapp(raw)
    client = get_odoo_client()

    for msg in messages:
        try:
            await client.call(
                "whatsapp.message",
                "process_inbound_webhook",
                [msg, provider_id],
            )
        except Exception as exc:
            _logger.error("Failed to forward WhatsApp message to Odoo: %s", exc)

    return {"ok": True, "forwarded": len(messages)}
