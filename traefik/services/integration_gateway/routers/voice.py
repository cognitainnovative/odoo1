"""Twilio Voice webhook receiver.

POST /webhooks/voice/incoming/{flow_id}    — inbound call (returns TwiML)
POST /webhooks/voice/speech/{call_id}      — STT gather result
POST /webhooks/voice/status/{call_id}      — call status update
"""
import logging
from urllib.parse import urljoin

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import Response

from normalizers.voice import normalise_twilio_voice, normalise_twilio_speech, normalise_twilio_status
from security.twilio import verify_twilio_signature

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/voice", tags=["voice"])


def _check_twilio(request: Request, params: dict, auth_token: str):
    url = str(request.url)
    sig = request.headers.get("X-Twilio-Signature", "")
    if not verify_twilio_signature(auth_token, url, params, sig):
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")


def _twiml(body: str) -> Response:
    return Response(content=body, media_type="text/xml")


@router.post("/incoming/{flow_id}")
async def inbound_call(flow_id: int, request: Request):
    from config import get_settings
    from odoo_client import get_odoo_client

    settings = get_settings()
    form = dict(await request.form())
    _check_twilio(request, form, settings.twilio_auth_token)

    payload = normalise_twilio_voice(form)
    client = get_odoo_client()

    try:
        twiml = await client.call(
            "voice.call.flow", "handle_inbound_call",
            [flow_id, payload],
        )
    except Exception as exc:
        _logger.error("Odoo handle_inbound_call failed: %s", exc)
        twiml = '<?xml version="1.0"?><Response><Say>Service temporarily unavailable.</Say></Response>'

    return _twiml(twiml or '<?xml version="1.0"?><Response><Hangup/></Response>')


@router.post("/speech/{call_id}")
async def speech_result(call_id: int, request: Request):
    from config import get_settings
    from odoo_client import get_odoo_client

    settings = get_settings()
    form = dict(await request.form())
    _check_twilio(request, form, settings.twilio_auth_token)

    payload = normalise_twilio_speech(form)
    client = get_odoo_client()

    try:
        twiml = await client.call("voice.call", "handle_speech_result", [call_id, payload])
    except Exception as exc:
        _logger.error("Odoo handle_speech_result failed: %s", exc)
        twiml = None

    return _twiml(twiml or '<?xml version="1.0"?><Response><Hangup/></Response>')


@router.post("/status/{call_id}")
async def call_status(call_id: int, request: Request):
    from config import get_settings
    from odoo_client import get_odoo_client

    settings = get_settings()
    form = dict(await request.form())
    _check_twilio(request, form, settings.twilio_auth_token)

    payload = normalise_twilio_status(form)
    client = get_odoo_client()

    try:
        await client.call("voice.call", "handle_call_status", [call_id, payload])
    except Exception as exc:
        _logger.error("Odoo handle_call_status failed: %s", exc)

    return {"ok": True}
