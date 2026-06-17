"""Voice call record — full lifecycle with transcription and sentiment."""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ESCALATION_SENTIMENT_ORDER = {
    "calm": 0,
    "positive": 0,
    "neutral": 1,
    "confused": 2,
    "frustrated": 3,
    "urgent": 4,
    "angry": 5,
}


class VoiceCall(models.Model):
    _name = "voice.call"
    _description = "Voice Call"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_time desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)
    provider_id = fields.Many2one("voice.provider", required=True)
    flow_id = fields.Many2one("voice.call.flow")

    # Call metadata
    direction = fields.Selection(
        [("inbound", "Inbound"), ("outbound", "Outbound")], default="inbound"
    )
    state = fields.Selection(
        [
            ("ringing", "Ringing"),
            ("active", "Active"),
            ("on_hold", "On Hold"),
            ("completed", "Completed"),
            ("missed", "Missed"),
            ("failed", "Failed"),
            ("transferred", "Transferred"),
        ],
        default="ringing",
        tracking=True,
    )

    from_number = fields.Char("Caller Number")
    to_number = fields.Char("Called Number")
    start_time = fields.Datetime("Call Start")
    end_time = fields.Datetime("Call End")
    duration_seconds = fields.Integer(compute="_compute_duration", store=True)

    # Recording (consent-gated)
    recording_consent_given = fields.Boolean("Recording Consent Given", default=False)
    recording_url = fields.Char("Recording URL", readonly=True)
    recording_sid = fields.Char("Recording SID", readonly=True)
    recording_duration = fields.Integer("Recording Duration (s)", readonly=True)

    # Transcription
    transcript_ids = fields.One2many("voice.transcript.line", "call_id", "Transcript")
    full_transcript = fields.Text(compute="_compute_full_transcript", store=True)

    # AI analysis
    ai_summary = fields.Text("AI Summary", readonly=True)
    call_outcome = fields.Selection(
        [
            ("resolved", "Resolved"),
            ("transferred", "Transferred to Agent"),
            ("callback_scheduled", "Callback Scheduled"),
            ("voicemail", "Voicemail Left"),
            ("no_answer", "No Answer"),
            ("abandoned", "Caller Abandoned"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
        readonly=True,
    )

    # Sentiment tracking
    current_sentiment = fields.Selection(
        [
            ("calm", "Calm"),
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("confused", "Confused"),
            ("frustrated", "Frustrated"),
            ("urgent", "Urgent"),
            ("angry", "Angry"),
        ],
        default="neutral",
        tracking=True,
    )
    peak_sentiment = fields.Selection(
        [
            ("calm", "Calm"),
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("confused", "Confused"),
            ("frustrated", "Frustrated"),
            ("urgent", "Urgent"),
            ("angry", "Angry"),
        ],
        readonly=True,
    )
    sentiment_escalation_triggered = fields.Boolean(readonly=True, default=False)

    # Linked records
    partner_id = fields.Many2one("res.partner", "Contact", ondelete="set null")
    lead_id = fields.Many2one("crm.lead", "Lead / Deal", ondelete="set null")
    ticket_id = fields.Many2one("helpdesk.ticket", ondelete="set null")

    # Provider call ID for webhook correlation
    provider_call_id = fields.Char("Provider Call ID", index=True)

    # Turn counter for escalation
    ai_turn_count = fields.Integer(default=0, readonly=True)

    @api.depends("from_number", "start_time", "direction")
    def _compute_name(self):
        for call in self:
            dt = str(call.start_time)[:16] if call.start_time else "?"
            call.name = f"Call {call.direction} {call.from_number or ''} {dt}"

    @api.depends("start_time", "end_time")
    def _compute_duration(self):
        for call in self:
            if call.start_time and call.end_time:
                call.duration_seconds = int((call.end_time - call.start_time).total_seconds())
            else:
                call.duration_seconds = 0

    @api.depends("transcript_ids.text", "transcript_ids.speaker")
    def _compute_full_transcript(self):
        for call in self:
            lines = call.transcript_ids
            call.full_transcript = "\n".join(
                f"{line.speaker.upper()}: {line.text}" for line in lines
            )

    def update_sentiment(self, new_sentiment: str):
        """Update current and peak sentiment; trigger escalation if threshold reached."""
        self.ensure_one()
        self.current_sentiment = new_sentiment

        # Update peak if more severe (or if no peak set yet)
        current_score = ESCALATION_SENTIMENT_ORDER.get(new_sentiment, 0)
        peak_score = (
            ESCALATION_SENTIMENT_ORDER.get(self.peak_sentiment, -1) if self.peak_sentiment else -1
        )
        if current_score > peak_score:
            self.peak_sentiment = new_sentiment

        # Check escalation threshold
        if self.provider_id:
            threshold = self.provider_id.escalation_sentiment_threshold or "angry"
            threshold_score = ESCALATION_SENTIMENT_ORDER.get(threshold, 5)
            if current_score >= threshold_score and not self.sentiment_escalation_triggered:
                self.sentiment_escalation_triggered = True
                return True  # Signal: escalate now
        return False

    def process_caller_speech(self, speech_text: str) -> dict:
        """Process a caller's speech turn: STT → sentiment → AI → TTS.

        Returns dict with:
          {reply_text, escalate, sentiment, citations, turn_count}
        """
        self.ensure_one()

        # Record transcript
        self.env["voice.transcript.line"].create(
            {"call_id": self.id, "speaker": "caller", "text": speech_text}
        )

        # Classify sentiment
        from ..lib.voice_providers import classify_sentiment

        sentiment = classify_sentiment(speech_text)
        should_escalate = self.update_sentiment(sentiment)

        self.ai_turn_count += 1

        # Check max turns
        flow = self.flow_id
        max_turns = flow.max_turns if flow else 5
        if self.ai_turn_count >= max_turns and not should_escalate:
            should_escalate = True

        if should_escalate:
            escalation_msg = (
                flow.escalation_message if flow else "Let me connect you with a team member."
            )
            self.env["voice.transcript.line"].create(
                {"call_id": self.id, "speaker": "system", "text": escalation_msg}
            )
            return {
                "reply_text": escalation_msg,
                "escalate": True,
                "sentiment": sentiment,
                "citations": [],
                "turn_count": self.ai_turn_count,
            }

        # Build system prompt
        system_prompt = (
            flow.ai_system_prompt if flow else None
        ) or "You are a helpful phone assistant. Be concise (max 2 sentences)."

        # Call AI with or without RAG
        use_rag = flow.use_rag if flow else True
        rag_limit = flow.rag_limit if flow else 3

        if use_rag:
            result = self.env["ai.service"].call_with_rag(
                speech_text,
                system_prompt=system_prompt,
                rag_limit=rag_limit,
                res_model=self._name,
                res_id=self.id,
            )
        else:
            result = self.env["ai.service"].call(
                speech_text,
                system_prompt=system_prompt,
                res_model=self._name,
                res_id=self.id,
            )

        reply = result.get("content", "I'm sorry, I couldn't process that. Please repeat.")
        citations = result.get("citations", [])

        # Record AI response
        self.env["voice.transcript.line"].create(
            {"call_id": self.id, "speaker": "assistant", "text": reply}
        )

        return {
            "reply_text": reply,
            "escalate": False,
            "sentiment": sentiment,
            "citations": citations,
            "turn_count": self.ai_turn_count,
        }

    def action_complete(self, outcome: str = "resolved"):
        """Mark call as completed, generate AI summary."""
        for call in self:
            call.write(
                {
                    "state": "completed",
                    "end_time": fields.Datetime.now(),
                    "call_outcome": outcome,
                }
            )
            call._generate_summary()
            if outcome == "callback_scheduled":
                call.activity_schedule(
                    "mail.mail_activity_data_todo",
                    note=(
                        f"Callback requested by {call.from_number or 'caller'}. "
                        f"Peak sentiment: {call.peak_sentiment or 'neutral'}. "
                        "Please call back at the earliest opportunity."
                    ),
                )

    def action_transfer(self):
        self.write({"state": "transferred", "call_outcome": "transferred"})

    def _generate_summary(self):
        """Generate AI summary of the call."""
        self.ensure_one()
        if not self.full_transcript:
            return
        result = self.env["ai.service"].call(
            f"Summarise this call in 2 sentences and classify the outcome:\n\n"
            f"{self.full_transcript[:1500]}",
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            self.ai_summary = result["content"][:500]


class VoiceTranscriptLine(models.Model):
    _name = "voice.transcript.line"
    _description = "Call Transcript Line"
    _order = "create_date"

    call_id = fields.Many2one("voice.call", required=True, ondelete="cascade", index=True)
    speaker = fields.Selection(
        [
            ("caller", "Caller"),
            ("assistant", "AI Assistant"),
            ("agent", "Human Agent"),
            ("system", "System"),
        ],
        required=True,
    )
    text = fields.Text(required=True)
    sentiment = fields.Selection(
        [
            ("calm", "Calm"),
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("confused", "Confused"),
            ("frustrated", "Frustrated"),
            ("urgent", "Urgent"),
            ("angry", "Angry"),
        ],
    )
    timestamp_ms = fields.Integer("Timestamp (ms)")
