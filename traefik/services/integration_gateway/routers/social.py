"""Meta Graph API social webhook receiver (Facebook / Instagram).

GET  /webhooks/social/{account_id}  — verification challenge
POST /webhooks/social/{account_id}  — inbound comments, messages, mentions
"""
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from normalizers.social import normalise_social
from security.meta import verify_meta_signature

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/social", tags=["social"])


@router.get("/{account_id}", response_class=PlainTextResponse)
async def social_verify(account_id: int, request: Request):
    params = dict(request.query_params)
    hub_mode = params.get("hub.mode")
    hub_challenge = params.get("hub.challenge", "")
    hub_token = params.get("hub.verify_token", "")

    from odoo_client import get_odoo_client
    try:
        client = get_odoo_client()
        result = await client.call(
            "social.account", "verify_webhook_token",
            [account_id, hub_mode, hub_token],
        )
    except Exception as exc:
        _logger.warning("Odoo social verify failed: %s", exc)
        result = hub_mode == "subscribe"

    if result:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{account_id}")
async def social_inbound(account_id: int, request: Request):
    from config import get_settings
    from odoo_client import get_odoo_client

    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_meta_signature(body, sig, settings.whatsapp_app_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = normalise_social(raw)
    client = get_odoo_client()

    for event in events:
        try:
            await client.call("social.message", "process_inbound_webhook", [account_id, event])
        except Exception as exc:
            _logger.error("Failed to forward social event to Odoo: %s", exc)

    return {"ok": True, "forwarded": len(events)}
