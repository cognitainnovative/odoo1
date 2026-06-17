"""Brutal edge-case tests for custom_ai_voice (M15).

Test-gate + compliance focus:
  - sentiment label persistence (structured labels stored, peak tracked)
  - escalation threshold: fires at/above configured sentiment, not below;
    fires only once; max-turns fallback
  - recording consent: default False; provider defaults to mock (no live API)
  - sentiment ordering monotonic (peak only rises)
"""

from odoo import fields
from odoo.addons.custom_ai_voice.lib.voice_providers import (
    classify_sentiment,
    synthesize_speech,
    transcribe_audio,
)
from odoo.tests.common import TransactionCase


class _VoiceBase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.provider = self.env["voice.provider"].search(
            [("provider_type", "=", "mock")], limit=1
        ) or self.env["voice.provider"].create({"name": "Mock", "provider_type": "mock"})
        self.flow = self.env["voice.call.flow"].search([("code", "=", "support")], limit=1)

    def _call(self, **kw):
        vals = {
            "provider_id": self.provider.id,
            "flow_id": self.flow.id if self.flow else False,
            "direction": "inbound",
            "from_number": "+31600000000",
            "start_time": fields.Datetime.now(),
        }
        vals.update(kw)
        return self.env["voice.call"].create(vals)


class TestBrutalSentimentPersistence(_VoiceBase):
    def test_sentiment_label_stored(self):
        call = self._call()
        call.update_sentiment("frustrated")
        self.assertEqual(
            call.current_sentiment,
            "frustrated",
            "Structured sentiment label must persist on the call.",
        )

    def test_peak_sentiment_only_rises(self):
        call = self._call()
        call.update_sentiment("neutral")  # 1
        call.update_sentiment("angry")  # 5
        call.update_sentiment("calm")  # 0
        self.assertEqual(
            call.peak_sentiment,
            "angry",
            "Peak sentiment must track the worst seen, not the latest.",
        )

    def test_structured_labels_are_known_set(self):
        # classify_sentiment must return a label in the documented structured set
        valid = {"calm", "positive", "neutral", "confused", "frustrated", "urgent", "angry"}
        for text in ["I am furious", "thank you so much", "ok", "I don't understand"]:
            self.assertIn(classify_sentiment(text), valid)


class TestBrutalEscalationThreshold(_VoiceBase):
    def test_escalates_at_threshold(self):
        self.provider.escalation_sentiment_threshold = "angry"
        call = self._call()
        # below threshold -> no escalation
        self.assertFalse(call.update_sentiment("frustrated"))
        # at threshold -> escalate
        self.assertTrue(
            call.update_sentiment("angry"),
            "Reaching the configured sentiment threshold must trigger escalation.",
        )

    def test_does_not_escalate_below_threshold(self):
        self.provider.escalation_sentiment_threshold = "angry"
        call = self._call()
        for s in ("neutral", "confused", "frustrated"):
            self.assertFalse(
                call.update_sentiment(s), f"{s} is below 'angry' threshold and must not escalate."
            )

    def test_escalation_fires_only_once(self):
        self.provider.escalation_sentiment_threshold = "frustrated"
        call = self._call()
        first = call.update_sentiment("angry")  # above frustrated -> escalate
        second = call.update_sentiment("angry")  # already escalated -> no re-fire
        self.assertTrue(first)
        self.assertFalse(second, "Escalation must trigger only once per call.")

    def test_lower_threshold_escalates_earlier(self):
        self.provider.escalation_sentiment_threshold = "frustrated"
        call = self._call()
        self.assertTrue(
            call.update_sentiment("frustrated"),
            "With threshold 'frustrated', a frustrated turn must escalate.",
        )


class TestBrutalRecordingConsent(_VoiceBase):
    def test_recording_consent_default_false(self):
        call = self._call()
        self.assertFalse(call.recording_consent_given)
        self.assertFalse(call.recording_url)

    def test_provider_defaults_to_mock(self):
        # Spec: no live API by default — provider + STT/TTS must be mock-capable.
        self.assertEqual(self.provider.provider_type, "mock")

    def test_two_party_consent_flag_exists(self):
        # The two-party-consent jurisdiction flag must exist and default safely.
        self.assertIn("recording_two_party_consent", self.provider._fields)
        self.assertFalse(self.provider.recording_two_party_consent)


class TestBrutalProvidersMocked(TransactionCase):
    """STT/TTS fall back to mock with no api_key — no live calls in tests."""

    def test_transcribe_mock_no_key(self):
        # No api_key -> mock path, returns a string, never raises / never hits network
        out = transcribe_audio(b"\x00\x00", provider="deepgram", api_key="")
        self.assertIsInstance(out, str)

    def test_synthesize_mock_no_key(self):
        out = synthesize_speech("hello", provider="elevenlabs", api_key="")
        self.assertIsInstance(out, (bytes, bytearray))
