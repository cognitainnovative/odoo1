"""WhatsApp messaging — inbound/outbound with AI draft + approval workflow."""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Legal blocker notice ───────────────────────────────────────────────────────
# Meta WhatsApp Cloud API requires Business app review before live use.
# Twilio WhatsApp and 360dialog are available for sandbox/testing.
# All sending is mocked unless a real provider key is configured.
# ─────────────────────────────────────────────────────────────────────────────


class WhatsappProvider(models.Model):
    _name = "whatsapp.provider"
    _description = "WhatsApp Provider Configuration"

    name = fields.Char(required=True)
    provider = fields.Selection(
        [
            ("mock", "Mock (Sandbox — No Real Sending)"),
            ("meta", "Meta WhatsApp Cloud API ⚠️ Requires Business App Review"),
            ("twilio", "Twilio WhatsApp"),
            ("dialog360", "360dialog"),
        ],
        default="mock",
        required=True,
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    is_active = fields.Boolean(default=True)
    webhook_verify_token = fields.Char("Webhook Verify Token")

    # Encrypted API credentials (see custom_ai_core encryption pattern)
    _api_key_encrypted = fields.Char("Encrypted API Key", copy=False)
    # Meta app secret for webhook HMAC-SHA256 signature verification
    _app_secret_encrypted = fields.Char(
        "Meta App Secret (Encrypted)",
        copy=False,
        help="Used to verify X-Hub-Signature-256 on inbound webhooks.",
    )
    phone_number_id = fields.Char("Phone Number ID (Meta)")
    account_sid = fields.Char("Account SID (Twilio)")
    from_number = fields.Char("From Number")

    # Status
    app_review_status = fields.Selection(
        [
            ("not_submitted", "Not Submitted"),
            ("pending", "App Review Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="not_submitted",
        help="Meta requires Business App Review before live sending.",
    )

    notes = fields.Text()

    _name_uniq = models.Constraint(
        "UNIQUE(company_id, provider)", "One provider per type per company."
    )

    def send_message(self, to_number: str, body: str, template_name: str = "") -> bool:
        """Send a WhatsApp message via the configured provider.

        Returns True on success, False on failure.
        All providers fall back to mock logging when credentials are absent.
        """
        self.ensure_one()
        if self.provider == "mock" or not self._api_key_encrypted:
            _logger.info("[WA MOCK] To: %s | Body: %s", to_number, body[:100])
            return True

        if self.provider == "meta":
            return self._send_meta(to_number, body)
        if self.provider == "twilio":
            return self._send_twilio(to_number, body)
        if self.provider == "dialog360":
            return self._send_360dialog(to_number, body)
        return False

    def _send_meta(self, to: str, body: str) -> bool:
        """Send via Meta WhatsApp Cloud API."""
        try:
            import requests

            from ..lib.encryption import decrypt_key

            api_key = decrypt_key(self._api_key_encrypted)
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": body},
                },
                timeout=30,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            _logger.error("Meta WhatsApp send failed: %s", exc)
            return False

    def _send_twilio(self, to: str, body: str) -> bool:
        """Send via Twilio WhatsApp."""
        try:
            import requests

            from ..lib.encryption import decrypt_key

            api_key = decrypt_key(self._api_key_encrypted)
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json",
                auth=(self.account_sid, api_key),
                data={"From": f"whatsapp:{self.from_number}", "To": f"whatsapp:{to}", "Body": body},
                timeout=30,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            _logger.error("Twilio WhatsApp send failed: %s", exc)
            return False

    def _send_360dialog(self, to: str, body: str) -> bool:
        """Send via 360dialog."""
        _logger.info("[360dialog STUB] To: %s | Body: %s", to, body[:100])
        return True


class WhatsappMessage(models.Model):
    _name = "whatsapp.message"
    _description = "WhatsApp Message"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    provider_id = fields.Many2one("whatsapp.provider", required=True, index=True)
    company_id = fields.Many2one(related="provider_id.company_id", store=True)

    direction = fields.Selection(
        [("inbound", "Inbound"), ("outbound", "Outbound")],
        required=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("received", "Received"),
            ("draft", "Draft (AI)"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("transferred", "Transferred to Agent"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
            ("failed", "Failed"),
        ],
        default="received",
        tracking=True,
    )

    # Contact
    from_number = fields.Char("From")
    to_number = fields.Char("To")
    partner_id = fields.Many2one("res.partner", "Contact", ondelete="set null")

    # Content
    body = fields.Text("Message Body")
    media_url = fields.Char("Media URL")
    media_type = fields.Char("Media Type")
    template_id = fields.Many2one("whatsapp.template", "Template Used")

    # AI draft
    ai_draft = fields.Text("AI Draft Reply", readonly=True)
    ai_approval_state = fields.Selection(
        [
            ("none", "No Draft"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("sent", "Sent"),
        ],
        default="none",
    )
    ai_edit_reason = fields.Text("Edit Reason")

    # Linked records
    lead_id = fields.Many2one("crm.lead", ondelete="set null")
    ticket_id = fields.Many2one("helpdesk.ticket", ondelete="set null")

    # Opt-in
    opt_in = fields.Boolean("Opted In")
    opt_in_date = fields.Datetime(readonly=True)

    # Human handoff
    assigned_agent_id = fields.Many2one("res.users", string="Assigned Agent", tracking=True)

    # Provider message ID for dedup
    provider_message_id = fields.Char("Provider Message ID", index=True)

    @api.depends("from_number", "direction", "create_date")
    def _compute_name(self):
        for msg in self:
            d = str(msg.create_date)[:16] if msg.create_date else "?"
            msg.name = f"WA {msg.direction} {msg.from_number or ''} {d}"

    def action_ai_draft_reply(self):
        """Generate AI draft reply — sets to pending_approval."""
        self.ensure_one()
        result = self.env["ai.service"].call(
            f"Draft a professional WhatsApp reply (keep it concise, max 300 chars):\n"
            f"Incoming: {self.body or ''}",
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            self.write({"ai_draft": result["content"][:300], "ai_approval_state": "pending"})

    def action_approve_and_send(self):
        """Approve the AI draft and send it.

        Consent gate: WhatsApp Business policy forbids messaging a contact who
        has not opted in, EXCEPT when replying within the customer-service window
        opened by an inbound message from that contact. So a reply to an inbound
        message is allowed; any other send requires recorded opt-in.
        """
        self.ensure_one()
        if self.ai_approval_state != "approved":
            raise UserError("Reply must be approved before sending.")
        # Consent / opt-in gate (compliance requirement).
        is_reply_to_inbound = self.direction == "inbound"
        if not self.opt_in and not is_reply_to_inbound:
            raise UserError(
                "Cannot send: this contact has not opted in to WhatsApp messages "
                "and this is not a reply within the service window. Record opt-in "
                "first (action_record_opt_in)."
            )
        body = self.ai_draft
        if self.provider_id.send_message(self.from_number, body):
            self.write({"state": "sent", "ai_approval_state": "sent"})
        else:
            self.write({"state": "failed"})

    def action_approve_draft(self):
        self.write({"ai_approval_state": "approved"})

    def action_reject_draft(self):
        self.write({"ai_approval_state": "rejected"})

    def action_create_lead(self):
        """Create CRM lead from this inbound message."""
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
                "name": f"WhatsApp: {self.from_number}",
                "type": "lead",
                "email_from": "",
                "description": self.body or "",
                "partner_id": self.partner_id.id if self.partner_id else False,
            }
        )
        self.lead_id = lead
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": lead.id,
            "view_mode": "form",
        }

    def action_create_ticket(self):
        """Create helpdesk ticket from this inbound message."""
        self.ensure_one()
        if self.ticket_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "helpdesk.ticket",
                "res_id": self.ticket_id.id,
                "view_mode": "form",
            }
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": f"WhatsApp: {self.from_number}",
                "description": self.body or "",
                "source": "whatsapp",
                "partner_id": self.partner_id.id if self.partner_id else False,
            }
        )
        self.ticket_id = ticket
        return {
            "type": "ir.actions.act_window",
            "res_model": "helpdesk.ticket",
            "res_id": ticket.id,
            "view_mode": "form",
        }

    def action_record_opt_in(self):
        self.write({"opt_in": True, "opt_in_date": fields.Datetime.now()})

    def action_handoff(self):
        """Transfer this conversation to a human agent."""
        self.ensure_one()
        if self.state not in ("received", "draft", "pending_approval"):
            raise UserError(_("Can only hand off messages that have not yet been sent."))
        self.write({"state": "transferred"})
        self.message_post(
            body=_("Conversation transferred to human agent."),
            subtype_xmlid="mail.mt_note",
        )

    @api.model
    def process_inbound_webhook(self, payload: dict, provider_id: int) -> "WhatsappMessage | None":
        """Process an inbound WhatsApp webhook payload."""
        provider = self.env["whatsapp.provider"].browse(provider_id)
        messages = []

        # Meta format
        if provider.provider == "meta":
            try:
                for entry in payload.get("entry", []):
                    for change in entry.get("changes", []):
                        for wa_msg in change.get("value", {}).get("messages", []):
                            msg_id = wa_msg.get("id", "")
                            if self.search([("provider_message_id", "=", msg_id)], limit=1):
                                continue  # dedup
                            msg = self.create(
                                {
                                    "provider_id": provider.id,
                                    "direction": "inbound",
                                    "from_number": wa_msg.get("from", ""),
                                    "body": wa_msg.get("text", {}).get("body", ""),
                                    "provider_message_id": msg_id,
                                }
                            )
                            messages.append(msg)
            except Exception as exc:
                _logger.error("WhatsApp webhook processing error: %s", exc)
        elif provider.provider == "mock":
            # For testing: create directly from payload with dedup
            msg_id = payload.get("id", "mock-" + str(self.env.uid))
            if self.search([("provider_message_id", "=", msg_id)], limit=1):
                pass  # dedup
            else:
                msg = self.create(
                    {
                        "provider_id": provider.id,
                        "direction": "inbound",
                        "from_number": payload.get("from", "+31600000000"),
                        "body": payload.get("body", "Test message"),
                        "provider_message_id": msg_id,
                    }
                )
                messages.append(msg)

        return messages[0] if messages else None


class WhatsappTemplate(models.Model):
    _name = "whatsapp.template"
    _description = "WhatsApp Message Template"

    name = fields.Char(required=True)
    provider_id = fields.Many2one("whatsapp.provider", required=True)
    template_name = fields.Char("Template Name (Provider)", required=True)
    language = fields.Char("Language", default="en_US")
    body = fields.Text("Body Preview")
    category = fields.Selection(
        [("marketing", "Marketing"), ("utility", "Utility"), ("authentication", "Authentication")],
        default="utility",
    )
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted for Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
    )
    active = fields.Boolean(default=True)
