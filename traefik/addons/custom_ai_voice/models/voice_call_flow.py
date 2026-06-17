"""Call flow builder — configurable per-purpose flows."""

from odoo import fields, models


class VoiceCallFlow(models.Model):
    _name = "voice.call.flow"
    _description = "Call Flow"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True, help="Used in webhook routing. E.g. 'support'")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    provider_id = fields.Many2one("voice.provider")
    is_active = fields.Boolean(default=True)

    flow_type = fields.Selection(
        [
            ("sales", "Sales / Lead Capture"),
            ("support", "Customer Support"),
            ("invoice", "Invoice / Billing"),
            ("planning", "Appointment / Planning"),
            ("rental", "Rental Availability"),
            ("complaint", "Complaint Handling"),
            ("callback", "Callback Request"),
            ("custom", "Custom"),
        ],
        default="support",
    )

    # Greeting
    greeting_text = fields.Text(
        "Greeting Message",
        default="Hello! Thank you for calling. How can I help you today?",
        translate=True,
    )

    # AI settings
    use_rag = fields.Boolean("Use Knowledge Base (RAG)", default=True)
    rag_limit = fields.Integer("RAG Result Limit", default=3)
    ai_system_prompt = fields.Text(
        "AI System Prompt",
        default=(
            "You are a helpful phone assistant. Keep responses concise and clear "
            "(max 2 sentences). The caller cannot see text, only hear you."
        ),
    )
    max_turns = fields.Integer("Max AI Turns Before Escalation", default=5)

    # Escalation
    escalation_message = fields.Text(
        "Escalation Message",
        default="Let me connect you with a team member who can help you further.",
        translate=True,
    )
    callback_offer_message = fields.Text(
        "Callback Offer Message",
        default="Would you like us to call you back? Press 1 for yes.",
        translate=True,
    )

    notes = fields.Text()
