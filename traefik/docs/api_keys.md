# API Keys Reference

All keys are optional. The platform boots and runs core CRM/Accounting/HRM/Inventory/Rental
without any external keys. Keys unlock AI, communication, and payment features.

| Key | Feature unlocked | Free tier | Degradation without key |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | AI drafting (Claude) | No | Uses mock provider |
| `OPENAI_API_KEY` | AI classification / embeddings | Yes (limited) | Uses mock / Ollama |
| `OLLAMA_BASE_URL` | Local LLM + embeddings | Free | Falls back to OpenAI |
| `DEEPGRAM_API_KEY` | Real-time STT for voice | Yes | Voice feature disabled |
| `ELEVENLABS_API_KEY` | TTS for voice agent | Yes (limited) | Voice feature disabled |
| `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` | VoIP / SMS | Pay-as-go | Phone/SMS disabled |
| `WHATSAPP_ACCESS_TOKEN` | WhatsApp Cloud API | Via Meta review | WhatsApp disabled |
| `MOLLIE_API_KEY` | iDEAL / payment links | Sandbox free | Payment links disabled |
| `GOCARDLESS_BANKDATA_*` | Live bank feed (PSD2) | Free EU | File import only |
| `MINDEE_API_KEY` | Invoice OCR (cloud) | 250 docs/month | Tesseract fallback |
| `META_APP_ID/SECRET` | FB/IG social inbox | Via Meta review | Social disabled |
| `SENTRY_DSN` | Error monitoring | Free tier | No error tracking |
| `APP_SECRET_ENCRYPTION_KEY` | Encrypted key storage | N/A | Required in prod |
