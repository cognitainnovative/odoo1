"""Integration Gateway — FastAPI service entry point.

Public webhook receiver that:
  1. Verifies provider signatures (Meta HMAC, Twilio HMAC)
  2. Normalises provider-specific payloads to a stable internal format
  3. Forwards to Odoo via JSON-RPC

Endpoints:
  GET  /health
  GET  /webhooks/whatsapp/{provider_id}    — Meta verification challenge
  POST /webhooks/whatsapp/{provider_id}    — inbound WhatsApp messages
  GET  /webhooks/social/{account_id}       — Meta verification challenge
  POST /webhooks/social/{account_id}       — inbound Facebook/Instagram events
  POST /webhooks/voice/incoming/{flow_id}  — Twilio inbound call (returns TwiML)
  POST /webhooks/voice/speech/{call_id}    — Twilio speech/gather result
  POST /webhooks/voice/status/{call_id}    — Twilio call status callback
  POST /webhooks/bank/import               — CAMT.053 / MT940 bank statement
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.health import router as health_router
from routers.whatsapp import router as whatsapp_router
from routers.voice import router as voice_router
from routers.social import router as social_router
from routers.bank import router as bank_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Integration Gateway",
    description="Webhook normalizer for WhatsApp, Voice, Social, and Bank integrations.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(whatsapp_router)
app.include_router(voice_router)
app.include_router(social_router)
app.include_router(bank_router)


if __name__ == "__main__":
    import uvicorn
    from config import get_settings
    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, log_level=s.log_level, reload=False)
