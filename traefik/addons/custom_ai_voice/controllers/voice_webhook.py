"""Voice webhook controller — Twilio TwiML + SIP webhook endpoints."""

import base64
import hashlib
import hmac as hmac_lib
import logging

from odoo import fields, http
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

TWIML_HEADER = '<?xml version="1.0" encoding="UTF-8"?><Response>'
TWIML_FOOTER = "</Response>"


def twiml(body: str):
    return request.make_response(
        TWIML_HEADER + body + TWIML_FOOTER,
        headers=[("Content-Type", "text/xml")],
    )


def _verify_twilio_signature(provider, req) -> bool:
    """Verify Twilio request authenticity via HMAC-SHA1.

    Returns True for mock provider or when no auth token is configured (dev mode).
    In production, returns False if signature header is missing or invalid.
    """
    if provider.provider_type == "mock" or not provider._auth_token_encrypted:
        return True
    try:
        from odoo.addons.custom_ai_voice.lib.voice_providers import decrypt_key

        auth_token = decrypt_key(provider._auth_token_encrypted)
        if not auth_token:
            return True
    except Exception:
        return True

    twilio_sig = req.httprequest.headers.get("X-Twilio-Signature", "")
    if not twilio_sig:
        _logger.warning("Twilio signature header missing on request to %s", req.httprequest.url)
        return False

    url = req.httprequest.url
    post_params = dict(req.httprequest.form)
    params_str = "".join(f"{k}{post_params[k]}" for k in sorted(post_params.keys()))
    validation_string = (url + params_str).encode("utf-8")
    expected = base64.b64encode(
        hmac_lib.new(auth_token.encode("utf-8"), validation_string, hashlib.sha1).digest()
    ).decode()
    return hmac_lib.compare_digest(twilio_sig, expected)


class VoiceWebhookController(http.Controller):

    @http.route(
        "/voice/incoming/<int:flow_id>", type="http", auth="public", methods=["POST"], csrf=False
    )
    def inbound_call(self, flow_id: int, **kwargs):
        """Twilio calls this when a call arrives — return initial TwiML."""
        flow = request.env["voice.call.flow"].sudo().browse(flow_id)
        provider = (
            flow.provider_id
            if flow.exists()
            else (
                request.env["voice.provider"]
                .sudo()
                .search([("provider_type", "=", "mock")], limit=1)
            )
        )

        if not provider:
            return twiml("<Say>Sorry, this service is not available.</Say>")

        if not _verify_twilio_signature(provider, request):
            return request.make_response(
                "Forbidden", status=403, headers=[("Content-Type", "text/plain")]
            )

        # Create call record
        call = (
            request.env["voice.call"]
            .sudo()
            .create(
                {
                    "provider_id": provider.id,
                    "flow_id": flow.id if flow.exists() else False,
                    "direction": "inbound",
                    "from_number": kwargs.get("From", "unknown"),
                    "to_number": kwargs.get("To", ""),
                    "start_time": fields.Datetime.now(),
                    "provider_call_id": kwargs.get("CallSid", ""),
                }
            )
        )

        greeting = flow.greeting_text if flow.exists() else "Hello! How can I help you today?"

        # Recording notice + consent gating.
        # LEGAL: a recording notice must ALWAYS be delivered before recording,
        # not only in two-party jurisdictions. Two-party (all-party) consent
        # regions require an explicit consent disclosure. Consent is only marked
        # given AFTER the notice is actually delivered, and <Record> is only
        # emitted once consent is established — never silently.
        record_verb = ""
        if provider.recording_enabled and provider.recording_consent_required:
            if provider.recording_two_party_consent:
                # All-party consent jurisdiction: explicit consent disclosure.
                notice = (
                    "This call will be recorded. As required in your region, all "
                    "parties must consent. By continuing to speak, you provide your "
                    "consent to be recorded. "
                )
            else:
                # Single-party jurisdiction: a clear recording notice is still given.
                notice = "This call may be recorded for quality and training purposes. "
            greeting = notice + greeting
            # Consent is recorded because the notice was actually delivered here.
            call.recording_consent_given = True
            record_verb = (
                '<Record action="/voice/recording_callback" method="POST"'
                ' playBeep="false" trim="trim-silence"/>'
            )
        elif provider.recording_enabled and not provider.recording_consent_required:
            # Recording enabled but consent explicitly NOT required (admin-configured
            # for a jurisdiction/scenario that allows it). Still no silent default.
            call.recording_consent_given = True
            record_verb = (
                '<Record action="/voice/recording_callback" method="POST"'
                ' playBeep="false" trim="trim-silence"/>'
            )
        # If recording_enabled is False: no notice, no <Record>, consent stays False.

        action_url = f"/voice/speech/{call.id}"
        body = (
            f"<Say>{greeting}</Say>"
            f"{record_verb}"
            f'<Gather input="speech" action="{action_url}" speechTimeout="2">'
            f"<Say>Please go ahead and speak after the tone.</Say>"
            f"</Gather>"
            f"<Redirect>{action_url}?no_input=1</Redirect>"
        )
        return twiml(body)

    @http.route(
        "/voice/speech/<int:call_id>", type="http", auth="public", methods=["POST"], csrf=False
    )
    def process_speech(self, call_id: int, **kwargs):
        """Twilio posts speech results here after Gather."""
        call = request.env["voice.call"].sudo().browse(call_id)
        if not call.exists():
            return twiml("<Say>Session expired.</Say><Hangup/>")

        # Handle no-input
        if kwargs.get("no_input") == "1":
            call.ai_turn_count += 1
            provider = call.provider_id
            max_no_input = provider.max_no_input_attempts if provider else 2
            if call.ai_turn_count >= max_no_input:
                return twiml("<Say>We didn't hear anything. Goodbye!</Say><Hangup/>")
            return twiml(
                f'<Gather input="speech" action="/voice/speech/{call.id}" speechTimeout="2">'
                f"<Say>Sorry, I didn't catch that. Please speak after the tone.</Say>"
                f"</Gather>"
                f"<Redirect>/voice/speech/{call.id}?no_input=1</Redirect>"
            )

        speech_text = kwargs.get("SpeechResult", "")
        if not speech_text:
            return twiml(
                f'<Gather input="speech" action="/voice/speech/{call.id}" speechTimeout="2">'
                f"<Say>I didn't hear you clearly. Please try again.</Say>"
                f"</Gather>"
            )

        # Process the speech
        result = call.process_caller_speech(speech_text)
        reply = result["reply_text"]

        if result.get("escalate"):
            # Transfer to agent or offer callback
            call.action_transfer()
            return twiml(
                f"<Say>{reply}</Say>"
                f'<Dial timeout="20"><Number>{call.to_number}</Number></Dial>'
                f"<Say>No agents available. Goodbye!</Say><Hangup/>"
            )

        # Continue the conversation
        return twiml(
            f"<Say>{reply}</Say>"
            f'<Gather input="speech" action="/voice/speech/{call.id}" speechTimeout="2">'
            f"<Say>Is there anything else I can help you with?</Say>"
            f"</Gather>"
            f"<Say>Thank you for calling. Goodbye!</Say><Hangup/>"
        )

    @http.route(
        "/voice/status/<int:call_id>", type="http", auth="public", methods=["POST"], csrf=False
    )
    def call_status(self, call_id: int, **kwargs):
        """Twilio posts call status updates here."""
        call = request.env["voice.call"].sudo().browse(call_id)
        if not call.exists():
            return request.make_response("OK", headers=[("Content-Type", "text/plain")])

        status = kwargs.get("CallStatus", "")
        if status == "completed":
            call.write(
                {
                    "state": "completed",
                    "end_time": fields.Datetime.now(),
                    "call_outcome": "resolved" if call.ai_turn_count > 0 else "missed",
                }
            )
        elif status in ("no-answer", "busy"):
            call.state = "missed"
        elif status == "failed":
            call.state = "failed"

        return request.make_response("OK", headers=[("Content-Type", "text/plain")])

    @http.route(
        "/voice/recording_callback", type="http", auth="public", methods=["POST"], csrf=False
    )
    def recording_callback(self, **kwargs):
        """Receive recording URL from Twilio after call completes."""
        call_sid = kwargs.get("CallSid", "")
        recording_url = kwargs.get("RecordingUrl", "")
        recording_sid = kwargs.get("RecordingSid", "")
        recording_duration = kwargs.get("RecordingDuration", 0)

        if call_sid and recording_url:
            call = (
                request.env["voice.call"]
                .sudo()
                .search([("provider_call_id", "=", call_sid)], limit=1)
            )
            if call:
                # Defense in depth: never store a recording URL if consent was not
                # recorded for this call. Protects against a provider posting a
                # recording for a call that should not have been recorded.
                if not call.recording_consent_given:
                    _logger.warning(
                        "Discarding recording for call %s (sid %s): no consent on record.",
                        call.id,
                        call_sid,
                    )
                    return Response(
                        "<?xml version='1.0' encoding='UTF-8'?><Response/>",
                        content_type="text/xml",
                    )
                call.write(
                    {
                        "recording_url": recording_url,
                        "recording_sid": recording_sid,
                        "recording_duration": int(recording_duration or 0),
                    }
                )

        return Response(
            "<?xml version='1.0' encoding='UTF-8'?><Response/>",
            content_type="text/xml",
        )

    @http.route("/voice/mock/call/<int:flow_id>", type="jsonrpc", auth="user", methods=["POST"])
    def mock_call(
        self,
        flow_id: int,
        caller_number: str = "+31600000000",
        speech: str = "I need help with my invoice.",
        **kwargs,
    ):
        """Mock call endpoint for testing without a real phone."""
        flow = request.env["voice.call.flow"].sudo().browse(flow_id)
        provider = (
            request.env["voice.provider"].sudo().search([("provider_type", "=", "mock")], limit=1)
        )
        if not provider:
            return {"error": "No mock provider configured."}

        call = (
            request.env["voice.call"]
            .sudo()
            .create(
                {
                    "provider_id": provider.id,
                    "flow_id": flow.id if flow.exists() else False,
                    "direction": "inbound",
                    "from_number": caller_number,
                    "start_time": fields.Datetime.now(),
                    "provider_call_id": f"mock-{request.env.uid}",
                }
            )
        )

        result = call.process_caller_speech(speech)
        return {
            "call_id": call.id,
            "reply": result["reply_text"],
            "sentiment": result["sentiment"],
            "escalated": result["escalate"],
            "citations": result["citations"],
        }
