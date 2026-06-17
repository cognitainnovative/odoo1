"""VoIP provider configuration — Twilio, SIP, or Mock."""

from odoo import fields, models


class VoiceProvider(models.Model):
    _name = "voice.provider"
    _description = "VoIP Provider"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    provider_type = fields.Selection(
        [
            ("mock", "Mock (Sandbox — No Real Calls)"),
            ("twilio", "Twilio Voice"),
            ("sip", "SIP / Asterisk / 3CX Webhook"),
        ],
        default="mock",
        required=True,
    )
    is_active = fields.Boolean(default=True)

    # Twilio credentials
    account_sid = fields.Char("Twilio Account SID")
    _auth_token_encrypted = fields.Char(copy=False)
    twilio_phone_number = fields.Char("Twilio Phone Number")
    twiml_app_sid = fields.Char("TwiML App SID")

    # SIP webhook secret — stored encrypted (set via env/secrets manager, not UI)
    _sip_webhook_secret_encrypted = fields.Char("Webhook Secret (Encrypted)", copy=False)

    # STT
    stt_provider = fields.Selection(
        [("mock", "Mock"), ("deepgram", "Deepgram"), ("whisper", "Whisper (local)")],
        default="mock",
    )
    stt_api_key_encrypted = fields.Char(copy=False)
    stt_language = fields.Char("STT Language", default="en")

    # TTS
    tts_provider = fields.Selection(
        [
            ("twiml", "TwiML <Say> (built-in)"),
            ("elevenlabs", "ElevenLabs"),
            ("openai", "OpenAI TTS"),
        ],
        default="twiml",
    )
    tts_api_key_encrypted = fields.Char(copy=False)
    tts_voice_id = fields.Char("Voice ID")

    # Call recording
    recording_enabled = fields.Boolean(
        "Call Recording Enabled",
        default=False,
        help="Gate behind explicit consent. See recording_consent_required.",
    )
    recording_consent_required = fields.Boolean(
        "Require Explicit Consent Before Recording",
        default=True,
    )
    recording_two_party_consent = fields.Boolean(
        "Two-Party Consent Jurisdiction",
        default=False,
        help="Enable for jurisdictions requiring all parties to consent (e.g. some US states).",
    )
    recording_retention_days = fields.Integer("Recording Retention (days)", default=90)

    # Escalation
    escalation_sentiment_threshold = fields.Selection(
        [("angry", "Angry"), ("frustrated", "Frustrated"), ("urgent", "Urgent")],
        default="angry",
        help="Escalate to human agent when sentiment reaches this level.",
    )
    max_no_input_attempts = fields.Integer("Max No-Input Attempts", default=2)

    notes = fields.Text()
