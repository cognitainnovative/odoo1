"""Chat session — one conversation thread between a visitor and the AI/agent."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Escalation trigger words that force human handoff
ESCALATION_TRIGGERS = [
    "lawsuit",
    "lawyer",
    "attorney",
    "legal",
    "sue",
    "court",
    "fraud",
    "criminal",
    "police",
    "emergency",
    "urgent help",
    "suicide",
    "harm",
    "dangerous",
]

# Phrases that indicate the visitor wants a human agent
HUMAN_REQUEST_PHRASES = [
    "speak to a human",
    "speak to human",
    "talk to an agent",
    "talk to a person",
    "real person",
    "actual person",
    "human agent",
    "live agent",
    "live support",
    "talk to someone",
    "connect me to",
    "transfer me",
    "agent please",
]

# Keywords associated with frustration/anger
FRUSTRATION_KEYWORDS = [
    "angry",
    "frustrated",
    "ridiculous",
    "useless",
    "terrible",
    "awful",
    "hate this",
    "waste of time",
    "not working",
    "still broken",
    "pathetic",
    "fed up",
    "unacceptable",
]

# High-risk topics (medical/financial/legal advice) where the bot must NOT
# answer and must route to a qualified human. Legal terms also appear in
# ESCALATION_TRIGGERS; these add the medical/financial advice surface the spec
# requires. Kept conservative to avoid over-escalating ordinary product queries.
HIGH_RISK_KEYWORDS = [
    # medical
    "diagnosis",
    "diagnose",
    "symptom",
    "medication",
    "prescription",
    "dosage",
    "side effect",
    "treatment for",
    "should i take",
    "medical advice",
    # financial advice (not ordinary pricing/billing)
    "invest",
    "investment advice",
    "financial advice",
    "tax advice",
    "should i buy shares",
    "mortgage advice",
    "pension advice",
    "what stocks",
]

# Confidence threshold below which AI escalates to human
ESCALATION_CONFIDENCE_THRESHOLD = 0.45


class ChatSession(models.Model):
    _name = "chat.session"
    _description = "Chat Session"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    visitor_id = fields.Many2one("chat.visitor", index=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)

    state = fields.Selection(
        [
            ("open", "Open — AI Answering"),
            ("escalated", "Escalated — Awaiting Agent"),
            ("assigned", "Assigned to Agent"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
        ],
        default="open",
        tracking=True,
        index=True,
    )
    escalation_reason = fields.Selection(
        [
            ("low_confidence", "Low AI Confidence"),
            ("human_requested", "Visitor Requested Human"),
            ("trigger_word", "Trigger Word Detected"),
            ("sentiment", "Frustration / Anger Detected"),
            ("high_risk", "High-Risk Topic (legal/financial/medical)"),
        ],
        readonly=True,
    )
    assigned_agent_id = fields.Many2one("res.users", "Assigned Agent")
    resolved_by_id = fields.Many2one("res.users", "Resolved By", readonly=True)
    resolved_date = fields.Datetime(readonly=True)

    # Visitor info (denormalised for quick access)
    visitor_name = fields.Char()
    visitor_email = fields.Char()
    visitor_company = fields.Char()
    language_code = fields.Char(default="en")

    # AI analysis
    sentiment = fields.Selection(
        [
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("frustrated", "Frustrated"),
            ("angry", "Angry"),
            ("urgent", "Urgent"),
        ],
        default="neutral",
    )
    ai_summary = fields.Text("AI Summary", readonly=True)
    suggested_next_action = fields.Text("Suggested Next Action", readonly=True)

    # Linked records
    lead_id = fields.Many2one("crm.lead", "Linked Lead", ondelete="set null")
    transcript_ids = fields.One2many("chat.transcript.line", "session_id", "Transcript")
    message_count = fields.Integer(compute="_compute_message_count")

    @api.depends("visitor_id", "create_date")
    def _compute_name(self):
        for sess in self:
            date = str(sess.create_date)[:16] if sess.create_date else "?"
            visitor = sess.visitor_name or (sess.visitor_id.token or "")[:8]
            sess.name = f"Chat {visitor} {date}"

    @api.depends("transcript_ids")
    def _compute_message_count(self):
        for sess in self:
            sess.message_count = len(sess.transcript_ids)

    def action_assign_to_me(self):
        self.write({"assigned_agent_id": self.env.user.id, "state": "assigned"})

    def action_resolve(self):
        for sess in self:
            sess.write(
                {
                    "state": "resolved",
                    "resolved_by_id": self.env.user.id,
                    "resolved_date": fields.Datetime.now(),
                }
            )
            sess._generate_ai_summary()

    def action_close(self):
        self.write({"state": "closed"})

    def action_create_lead(self):
        """Create a CRM lead from this chat session."""
        self.ensure_one()
        if self.lead_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "crm.lead",
                "res_id": self.lead_id.id,
                "view_mode": "form",
            }
        lead = self.env["crm.lead"].create(
            {
                "name": f"Chat lead: {self.visitor_name or 'Unknown'}",
                "type": "lead",
                "email_from": self.visitor_email or "",
                "partner_name": self.visitor_company or "",
                "description": self.ai_summary or "",
            }
        )
        self.lead_id = lead
        if self.visitor_id:
            self.visitor_id.lead_id = lead
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": lead.id,
            "view_mode": "form",
        }

    def escalate(self, reason: str):
        """Escalate this session to a human agent and notify the team.

        Routing: prefer agents who have available_for_chat=True; fall back to all
        internal users so escalations never go unnoticed.
        """
        self.write({"state": "escalated", "escalation_reason": reason})
        self.message_post(
            body=(
                f"<b>Chat escalated</b> — reason: {reason}<br/>"
                f"Visitor: {self.visitor_name or 'Anonymous'} "
                f"({self.visitor_email or 'no email'})"
            ),
            subtype_xmlid="mail.mt_note",
        )
        try:
            # Prefer currently-available chat agents
            available = self.env["res.users"].search(
                [("share", "=", False), ("active", "=", True), ("available_for_chat", "=", True)]
            )
            if available:
                agent_partners = available.mapped("partner_id")
            else:
                # No one marked available — fall back to all internal users
                agent_partners = (
                    self.env["res.users"]
                    .search([("share", "=", False), ("active", "=", True)])
                    .mapped("partner_id")
                )
            if agent_partners:
                self.message_post(
                    body=f"New escalated chat from {self.visitor_name or 'Anonymous'}: "
                    f"{reason}. Please check the Live Chat queue.",
                    partner_ids=agent_partners.ids,
                    subtype_xmlid="mail.mt_comment",
                )
        except Exception:
            pass  # Never block escalation due to notification failure

    def _generate_ai_summary(self):
        """Ask AI to summarise the conversation."""
        self.ensure_one()
        if not self.transcript_ids:
            return
        transcript_text = "\n".join(
            f"{line.role.upper()}: {line.content}" for line in self.transcript_ids[:20]
        )
        result = self.env["ai.service"].call(
            f"Summarise this chat conversation in 2-3 sentences and suggest a next action:\n\n"
            f"{transcript_text}",
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            self.ai_summary = result["content"][:500]

    @api.model
    def process_message(
        self,
        session_id: int,
        user_message: str,
        visitor_name: str = "",
        visitor_email: str = "",
    ) -> dict:
        """Process an incoming chat message and return AI response.

        Returns:
            {
                "reply": str,
                "escalated": bool,
                "escalation_reason": str | None,
                "citations": list,
                "session_id": int,
            }
        """
        session = self.browse(session_id)
        if not session.exists():
            raise UserError("Chat session not found.")

        # Update visitor info
        if visitor_name and not session.visitor_name:
            session.visitor_name = visitor_name
        if visitor_email and not session.visitor_email:
            session.visitor_email = visitor_email

        # Record user message
        self.env["chat.transcript.line"].create(
            {"session_id": session.id, "role": "user", "content": user_message}
        )

        # Check for trigger words, human-request phrases, and frustration (case-insensitive)
        lower_msg = user_message.lower()

        def _escalate_with_reply(reason: str, reply_text: str) -> dict:
            session.escalate(reason)
            self.env["chat.transcript.line"].create(
                {"session_id": session.id, "role": "assistant", "content": reply_text}
            )
            return {
                "reply": reply_text,
                "escalated": True,
                "escalation_reason": reason,
                "citations": [],
                "session_id": session.id,
            }

        for trigger in ESCALATION_TRIGGERS:
            if trigger in lower_msg:
                return _escalate_with_reply(
                    "trigger_word",
                    "I understand this is an important matter. "
                    "I'm connecting you with a human agent who can better assist you.",
                )

        for phrase in HUMAN_REQUEST_PHRASES:
            if phrase in lower_msg:
                return _escalate_with_reply(
                    "human_requested",
                    "Of course! Let me connect you with one of our team members right away.",
                )

        # High-risk topics (medical/financial/legal) must escalate, never be
        # answered by the bot — compliance requirement.
        for kw in HIGH_RISK_KEYWORDS:
            if kw in lower_msg:
                return _escalate_with_reply(
                    "high_risk",
                    "This is an important topic that deserves expert attention. "
                    "Let me connect you with a qualified member of our team.",
                )

        frustration_detected = any(kw in lower_msg for kw in FRUSTRATION_KEYWORDS)
        if frustration_detected:
            session.sentiment = "frustrated"
            return _escalate_with_reply(
                "sentiment",
                "I'm sorry this has been frustrating. "
                "Let me get a team member to assist you personally.",
            )

        # Call AI with RAG
        result = self.env["ai.service"].call_with_rag(
            user_message,
            rag_limit=3,
            res_model=self._name,
            res_id=session.id,
        )

        ai_reply = result.get("content", "I'm sorry, I couldn't process that.")
        citations = result.get("citations", [])
        confidence = 1.0 if result.get("ok") else 0.0

        # Escalate on low confidence
        if confidence < ESCALATION_CONFIDENCE_THRESHOLD and not result.get("ok"):
            session.escalate("low_confidence")
            ai_reply = (
                "I want to make sure you get the best answer. "
                "Let me connect you with one of our team members."
            )

        self.env["chat.transcript.line"].create(
            {"session_id": session.id, "role": "assistant", "content": ai_reply}
        )

        return {
            "reply": ai_reply,
            "escalated": session.state == "escalated",
            "escalation_reason": (
                session.escalation_reason if session.state == "escalated" else None
            ),
            "citations": citations,
            "session_id": session.id,
        }

    def action_transfer_to_agent(self, agent_id: int):
        """Transfer session to a different agent."""
        self.ensure_one()
        new_agent = self.env["res.users"].browse(agent_id)
        if not new_agent.exists():
            raise UserError("Target agent not found.")
        self.write({"assigned_agent_id": agent_id, "state": "assigned"})
        self.message_post(
            body=f"Session transferred to {new_agent.name}.",
            subtype_xmlid="mail.mt_note",
        )

    def action_suggest_reply(self) -> dict:
        """Ask AI to suggest a reply based on recent transcript context."""
        self.ensure_one()
        if not self.transcript_ids:
            return {"suggestion": ""}
        transcript_text = "\n".join(
            f"{line.role.upper()}: {line.content}" for line in self.transcript_ids[-6:]
        )
        result = self.env["ai.service"].call(
            f"You are a customer support agent. "
            f"Based on this conversation, suggest a helpful, concise reply:\n\n"
            f"{transcript_text}\n\nAGENT REPLY:",
            res_model=self._name,
            res_id=self.id,
        )
        return {"suggestion": result.get("content", "") if result.get("ok") else ""}


class ChatTranscriptLine(models.Model):
    _name = "chat.transcript.line"
    _description = "Chat Transcript Line"
    _order = "create_date"

    session_id = fields.Many2one("chat.session", required=True, ondelete="cascade", index=True)
    role = fields.Selection(
        [("user", "Visitor"), ("assistant", "AI"), ("agent", "Human Agent")],
        required=True,
    )
    content = fields.Text(required=True)
    # AI-specific
    ai_confidence = fields.Float(digits=(4, 2))
    was_rag = fields.Boolean("Used RAG")


class ChatConfig(models.Model):
    """Per-company chatbot configuration."""

    _name = "chat.config"
    _description = "Chatbot Configuration"
    _rec_name = "company_id"

    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    is_enabled = fields.Boolean("Chatbot Enabled", default=True)
    greeting_message = fields.Char(
        "Greeting Message",
        default="Hi! 👋 How can I help you today?",
        translate=True,
    )
    offline_message = fields.Char(
        "Offline Message",
        default="We're currently offline. Leave your email and we'll get back to you!",
        translate=True,
    )
    escalation_message = fields.Char(
        "Escalation Message",
        default="Let me connect you with a team member who can help.",
        translate=True,
    )
    collect_email = fields.Boolean("Ask for Email", default=True)
    collect_company = fields.Boolean("Ask for Company Name", default=False)
    # Show widget on these page paths (comma-separated, empty = all pages)
    allowed_paths = fields.Char("Show on Pages")
    primary_color = fields.Char("Widget Color", default="#1E40AF")
    # ── External channel integrations ────────────────────────────────────────
    whatsapp_enabled = fields.Boolean(
        "WhatsApp Channel",
        default=False,
        help=(
            "EXTERNAL INTEGRATION — requires a Twilio or Vonage WhatsApp Business API "
            "account. Configure credentials in Settings → AI Integrations → WhatsApp "
            "Provider before enabling. Do NOT enable without valid provider credentials."
        ),
    )
    whatsapp_phone_number = fields.Char(
        "WhatsApp Business Number",
        help=(
            "Your registered WhatsApp Business phone number (E.164 format, e.g. +31612345678). "
            "Leave empty until provider credentials are confirmed."
        ),
    )

    _company_uniq = models.Constraint("UNIQUE(company_id)", "One config per company.")


class ChatCannedReply(models.Model):
    """Pre-written replies that agents can insert with a shortcut."""

    _name = "chat.canned.reply"
    _description = "Canned Reply"
    _order = "shortcut"

    shortcut = fields.Char(
        required=True,
        help="Short code — type this in the agent chat to insert the message.",
    )
    name = fields.Char("Label", required=True)
    message = fields.Text("Message", required=True)
    category = fields.Char("Category", help="Grouping label (e.g. Pricing, Technical, General).")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    active = fields.Boolean(default=True)

    _shortcut_company_uniq = models.Constraint(
        "UNIQUE(shortcut, company_id)",
        "Shortcut must be unique per company.",
    )
