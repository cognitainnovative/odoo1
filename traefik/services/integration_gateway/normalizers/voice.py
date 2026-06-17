"""Normalise Twilio Voice webhook payloads to Odoo-friendly dicts."""
from __future__ import annotations


def normalise_twilio_voice(params: dict) -> dict:
    """Inbound call (TwiML webhook) → normalised call-start event."""
    return {
        "call_sid": params.get("CallSid", ""),
        "from_number": params.get("From", ""),
        "to_number": params.get("To", ""),
        "direction": params.get("Direction", "inbound"),
        "call_status": params.get("CallStatus", "ringing"),
        "caller_name": params.get("CallerName", ""),
        "caller_city": params.get("CallerCity", ""),
        "caller_country": params.get("CallerCountry", ""),
    }


def normalise_twilio_speech(params: dict) -> dict:
    """Speech result (Gather verb callback) → normalised speech event."""
    return {
        "call_sid": params.get("CallSid", ""),
        "speech_result": params.get("SpeechResult", ""),
        "confidence": float(params.get("Confidence", 0.0)),
        "stability": float(params.get("Stability", 0.0)),
    }


def normalise_twilio_status(params: dict) -> dict:
    """Call status callback → normalised call-end event."""
    return {
        "call_sid": params.get("CallSid", ""),
        "call_status": params.get("CallStatus", ""),
        "call_duration": int(params.get("CallDuration", 0) or 0),
        "recording_url": params.get("RecordingUrl", ""),
        "recording_sid": params.get("RecordingSid", ""),
    }
