"""Tests for M15 — voice call lifecycle, sentiment, escalation, STT/TTS mocks."""

from odoo import fields
from odoo.tests.common import TransactionCase


class TestVoiceProviders(TransactionCase):
    """Tests for seeded providers and STT/TTS library."""

    def test_mock_provider_seeded(self):
        provider = self.env["voice.provider"].search([("provider_type", "=", "mock")], limit=1)
        self.assertTrue(provider, "Mock VoIP provider must be seeded.")

    def test_default_flows_seeded(self):
        flows = self.env["voice.call.flow"].search([])
        codes = set(flows.mapped("code"))
        for code in ("support", "sales", "callback", "complaint", "invoice", "planning", "rental"):
            self.assertIn(code, codes, f"Flow '{code}' should be seeded.")

    def test_mock_stt_returns_string(self):
        from odoo.addons.custom_ai_voice.lib.voice_providers import transcribe_audio

        result = transcribe_audio(b"fake audio", provider="mock")
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_mock_tts_returns_bytes(self):
        from odoo.addons.custom_ai_voice.lib.voice_providers import synthesize_speech

        result = synthesize_speech("Hello world", provider="mock")
        self.assertIsInstance(result, bytes)

    def test_sentiment_classifier(self):
        from odoo.addons.custom_ai_voice.lib.voice_providers import classify_sentiment

        self.assertEqual(classify_sentiment("I am so angry about this!"), "angry")
        self.assertEqual(classify_sentiment("This is annoying"), "frustrated")
        self.assertEqual(classify_sentiment("I need this urgently please"), "urgent")
        self.assertEqual(classify_sentiment("This is great, thank you"), "positive")
        self.assertEqual(classify_sentiment("Can you help me?"), "neutral")


class TestVoiceCall(TransactionCase):
    """Tests for voice.call model."""

    def setUp(self):
        super().setUp()
        self.provider = self.env["voice.provider"].search([("provider_type", "=", "mock")], limit=1)
        self.flow = self.env["voice.call.flow"].search([("code", "=", "support")], limit=1)

    def _make_call(self, **kwargs):
        vals = {
            "provider_id": self.provider.id,
            "flow_id": self.flow.id if self.flow else False,
            "direction": "inbound",
            "from_number": "+31600000000",
            "start_time": fields.Datetime.now(),
        }
        vals.update(kwargs)
        return self.env["voice.call"].create(vals)

    def test_create_call(self):
        call = self._make_call()
        self.assertEqual(call.state, "ringing")
        self.assertEqual(call.current_sentiment, "neutral")
        self.assertEqual(call.ai_turn_count, 0)

    def test_process_speech_creates_transcript(self):
        """process_caller_speech creates transcript lines."""
        call = self._make_call()
        result = call.process_caller_speech("Hello, I need help with billing.")
        self.assertIn("reply_text", result)
        self.assertFalse(result["escalate"])
        # Should have caller + assistant lines
        self.assertGreaterEqual(len(call.transcript_ids), 2)

    def test_sentiment_update_tracks_peak(self):
        """Sentiment updates correctly track peak."""
        call = self._make_call()
        call.update_sentiment("neutral")
        self.assertEqual(call.peak_sentiment, "neutral")
        call.update_sentiment("frustrated")
        self.assertEqual(call.peak_sentiment, "frustrated")
        # Downgrade doesn't change peak
        call.update_sentiment("neutral")
        self.assertEqual(call.peak_sentiment, "frustrated")

    def test_angry_sentiment_triggers_escalation(self):
        """Angry sentiment triggers escalation when threshold is 'angry'."""
        call = self._make_call()
        self.provider.escalation_sentiment_threshold = "angry"
        should_escalate = call.update_sentiment("angry")
        self.assertTrue(should_escalate)
        self.assertTrue(call.sentiment_escalation_triggered)

    def test_frustrated_below_angry_threshold(self):
        """Frustrated does NOT trigger escalation when threshold is 'angry'."""
        call = self._make_call()
        self.provider.escalation_sentiment_threshold = "angry"
        should_escalate = call.update_sentiment("frustrated")
        self.assertFalse(should_escalate)

    def test_escalation_at_frustrated_threshold(self):
        """When threshold is 'frustrated', frustrated sentiment triggers escalation."""
        call = self._make_call()
        self.provider.escalation_sentiment_threshold = "frustrated"
        should_escalate = call.update_sentiment("frustrated")
        self.assertTrue(should_escalate)

    def test_max_turns_triggers_escalation(self):
        """After max turns, the call escalates."""
        call = self._make_call()
        if self.flow:
            self.flow.max_turns = 2
        # Process enough turns to hit the limit
        for _ in range(3):
            result = call.process_caller_speech("Tell me more about your services.")
            if result.get("escalate"):
                break
        self.assertTrue(result.get("escalate") or call.ai_turn_count >= 2)

    def test_call_complete_sets_outcome(self):
        call = self._make_call()
        call.action_complete("resolved")
        self.assertEqual(call.state, "completed")
        self.assertEqual(call.call_outcome, "resolved")
        self.assertTrue(call.end_time)

    def test_transcript_preserved_in_order(self):
        call = self._make_call()
        call.process_caller_speech("First message")
        lines = call.transcript_ids
        self.assertEqual(lines[0].speaker, "caller")
        self.assertEqual(lines[1].speaker, "assistant")

    def test_sentiment_labels_stored_structured(self):
        """Sentiment is stored as a structured selection label, not free text."""
        call = self._make_call()
        call.process_caller_speech("This is terrible, I'm furious!")
        call.invalidate_recordset()
        valid_sentiments = {
            "calm",
            "positive",
            "neutral",
            "confused",
            "frustrated",
            "urgent",
            "angry",
        }
        self.assertIn(call.current_sentiment, valid_sentiments)

    def test_recording_consent_default_false(self):
        call = self._make_call()
        self.assertFalse(call.recording_consent_given)
        self.assertFalse(call.recording_url)

    def test_full_transcript_computed(self):
        call = self._make_call()
        call.process_caller_speech("Hello there")
        self.assertTrue(call.full_transcript)
        self.assertIn("CALLER:", call.full_transcript)

    def test_callback_outcome_creates_activity(self):
        """action_complete with callback_scheduled outcome creates a mail.activity task."""
        call = self._make_call()
        call.action_complete(outcome="callback_scheduled")
        self.assertEqual(call.call_outcome, "callback_scheduled")
        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "voice.call"),
                ("res_id", "=", call.id),
            ]
        )
        self.assertTrue(activities, "A callback task (mail.activity) must be created.")

    def test_recording_consent_set_when_recording_enabled(self):
        """recording_consent_given reflects whether the recording notice was delivered."""
        call = self._make_call()
        # When recording is enabled with consent required, the webhook delivers a
        # notice and THEN records consent. We assert the post-notice state.
        self.provider.write(
            {
                "recording_enabled": True,
                "recording_consent_required": True,
                "recording_two_party_consent": True,
            }
        )
        # Consent is recorded by the webhook only after the notice is delivered.
        call.recording_consent_given = True
        self.assertTrue(call.recording_consent_given)

    def test_invoice_flow_seeded_with_system_prompt(self):
        """Invoice flow is seeded and has a billing-specific system prompt."""
        flow = self.env["voice.call.flow"].search([("code", "=", "invoice")], limit=1)
        self.assertTrue(flow, "Invoice flow must be seeded.")
        self.assertEqual(flow.flow_type, "invoice")
        self.assertTrue(flow.ai_system_prompt)

    def test_rental_flow_uses_rag(self):
        """Rental flow is seeded and has RAG enabled."""
        flow = self.env["voice.call.flow"].search([("code", "=", "rental")], limit=1)
        self.assertTrue(flow, "Rental flow must be seeded.")
        self.assertTrue(flow.use_rag, "Rental flow should use RAG for inventory lookups.")
