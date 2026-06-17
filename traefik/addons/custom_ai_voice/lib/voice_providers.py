"""STT, TTS and VoIP provider abstractions — all fall back to mock."""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

_logger = logging.getLogger(__name__)


# ── Encryption helpers (Fernet, keyed from APP_SECRET_ENCRYPTION_KEY) ──────────


def _get_fernet():
    key = os.environ.get("APP_SECRET_ENCRYPTION_KEY", "").encode()
    if not key:
        _logger.warning(
            "APP_SECRET_ENCRYPTION_KEY not set — encryption unavailable; "
            "set this environment variable in production."
        )
        return None
    try:
        return Fernet(key)
    except Exception:
        _logger.error("APP_SECRET_ENCRYPTION_KEY is not a valid Fernet key.")
        return None


def encrypt_key(plaintext: str) -> str:
    """Encrypt a provider credential for storage.

    Returns an empty string if APP_SECRET_ENCRYPTION_KEY is not configured.
    """
    fernet = _get_fernet()
    if fernet is None:
        return ""
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    """Decrypt a stored provider credential.

    Returns an empty string if APP_SECRET_ENCRYPTION_KEY is not configured
    or if the token is invalid.
    """
    if not encrypted:
        return ""
    fernet = _get_fernet()
    if fernet is None:
        return ""
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except (InvalidToken, Exception):
        return ""


# ── Speech-to-Text ─────────────────────────────────────────────────────────────


def transcribe_audio(
    audio_bytes: bytes, provider: str = "whisper", api_key: str = "", language: str = "en"
) -> str:
    """Transcribe audio bytes to text.

    Providers:
      - mock: returns a fixed test transcription
      - whisper: OpenAI Whisper self-hosted (batch)
      - deepgram: Deepgram real-time API
    """
    if provider == "mock" or not api_key:
        return "[MOCK TRANSCRIPTION] Hello, I need help with my account."

    if provider == "deepgram":
        try:
            import requests

            resp = requests.post(
                "https://api.deepgram.com/v1/listen?language=" + language,
                headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"},
                data=audio_bytes,
                timeout=30,
            )
            if resp.ok:
                return resp.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        except Exception as exc:
            _logger.warning("Deepgram STT failed: %s", exc)
        return ""

    if provider == "whisper":
        try:
            import requests

            resp = requests.post(
                "http://localhost:9000/asr",  # typical Whisper self-hosted endpoint
                files={"audio_file": audio_bytes},
                data={"task": "transcribe", "language": language},
                timeout=60,
            )
            if resp.ok:
                return resp.json().get("text", "")
        except Exception as exc:
            _logger.warning("Whisper STT failed: %s", exc)
        return ""

    return ""


# ── Text-to-Speech ─────────────────────────────────────────────────────────────


def synthesize_speech(
    text: str, provider: str = "elevenlabs", api_key: str = "", voice_id: str = ""
) -> bytes:
    """Synthesize text to audio bytes (MP3/WAV).

    Providers:
      - mock: returns empty bytes (caller handles gracefully)
      - elevenlabs: ElevenLabs API
      - openai: OpenAI TTS API
    """
    if provider == "mock" or not api_key:
        _logger.debug("[TTS MOCK] Would say: %s", text[:80])
        return b""  # Caller generates TwiML <Say> instead

    if provider == "elevenlabs":
        try:
            import requests

            vid = voice_id or "21m00Tcm4TlvDq8ikWAM"
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_monolingual_v1"},
                timeout=30,
            )
            if resp.ok:
                return resp.content
        except Exception as exc:
            _logger.warning("ElevenLabs TTS failed: %s", exc)
        return b""

    if provider == "openai":
        try:
            import requests

            resp = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "tts-1", "input": text, "voice": voice_id or "alloy"},
                timeout=30,
            )
            if resp.ok:
                return resp.content
        except Exception as exc:
            _logger.warning("OpenAI TTS failed: %s", exc)
        return b""

    return b""


# ── Sentiment classifier ────────────────────────────────────────────────────────

SENTIMENT_KEYWORDS = {
    "angry": ["angry", "furious", "unacceptable", "lawsuit", "terrible", "disgusting"],
    "frustrated": ["frustrated", "annoying", "keep telling", "again and again", "never works"],
    "urgent": ["urgent", "emergency", "asap", "immediately", "critical", "right now"],
    "confused": ["confused", "don't understand", "what do you mean", "unclear"],
    "positive": ["great", "excellent", "thank you", "helpful", "love it", "perfect"],
}


def classify_sentiment(text: str) -> str:
    """Rule-based sentiment classification from transcript text.

    Returns one of: calm | positive | neutral | confused | frustrated | angry | urgent
    """
    text_lower = text.lower()
    for sentiment, keywords in SENTIMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return sentiment
    return "neutral"


def build_twiml_say(text: str, voice: str = "alice", language: str = "en-US") -> str:
    """Build a TwiML <Say> verb."""
    import xml.sax.saxutils as su

    return f'<Say voice="{voice}" language="{language}">{su.escape(text)}</Say>'


def build_twiml_gather(action_url: str, num_digits: int = 0, speech_timeout: str = "2") -> str:
    """Build a TwiML <Gather> for speech input."""
    attrs = f'input="speech" action="{action_url}" speechTimeout="{speech_timeout}"'
    if num_digits:
        attrs += f' numDigits="{num_digits}"'
    return f"<Gather {attrs}>"
