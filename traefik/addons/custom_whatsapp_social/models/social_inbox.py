"""Social inbox — messages/comments/mentions from social platforms."""

import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    _name = "social.account"
    _description = "Social Media Account"

    name = fields.Char(required=True)
    platform = fields.Selection(
        [
            ("mock", "Mock (Sandbox)"),
            ("facebook", "Facebook / Instagram ⚠️ Meta App Review Required"),
            ("instagram", "Instagram (via Meta)"),
            ("linkedin", "LinkedIn"),
            ("twitter", "X / Twitter ⚠️ Paid API Tier Required"),
        ],
        required=True,
        default="mock",
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    is_active = fields.Boolean(default=True)
    _api_key_encrypted = fields.Char(copy=False)
    page_id = fields.Char("Page / Profile ID")
    username = fields.Char()

    # Approval blocker status
    app_review_status = fields.Selection(
        [("not_submitted", "Not Submitted"), ("pending", "Pending"), ("approved", "Approved")],
        default="not_submitted",
    )
    notes = fields.Text()


class SocialMessage(models.Model):
    _name = "social.message"
    _description = "Social Inbox Message"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    account_id = fields.Many2one("social.account", required=True, index=True)
    company_id = fields.Many2one(related="account_id.company_id", store=True)

    message_type = fields.Selection(
        [
            ("comment", "Comment"),
            ("dm", "Direct Message"),
            ("mention", "Mention"),
            ("review", "Review"),
        ],
        default="comment",
    )
    platform = fields.Selection(related="account_id.platform", store=True)
    direction = fields.Selection(
        [("inbound", "Inbound"), ("outbound", "Outbound")], default="inbound"
    )

    state = fields.Selection(
        [
            ("new", "New"),
            ("draft", "AI Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("sent", "Sent"),
            ("escalated", "Escalated"),
            ("archived", "Archived"),
        ],
        default="new",
        tracking=True,
    )

    # Content
    author_name = fields.Char()
    author_id_external = fields.Char("External Author ID")
    body = fields.Text()
    post_url = fields.Char("Post URL")
    external_message_id = fields.Char(index=True)

    # AI
    sentiment = fields.Selection(
        [
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("negative", "Negative"),
            ("angry", "Angry"),
        ],
        readonly=True,
    )
    ai_draft_reply = fields.Text(readonly=True)
    ai_final_reply = fields.Text()
    ai_edit_reason = fields.Text()

    # Links
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    lead_id = fields.Many2one("crm.lead", ondelete="set null")
    ticket_id = fields.Many2one("helpdesk.ticket", ondelete="set null")

    def _compute_name(self):
        for m in self:
            m.name = f"{m.platform or ''} {m.message_type} {str(m.create_date or '')[:16]}"

    _VALID_SENTIMENTS = {"positive", "neutral", "negative", "angry"}

    def action_ai_draft_reply(self):
        for msg in self:
            result = self.env["ai.service"].call(
                f"For this social media message return JSON only with keys:\n"
                f"  reply (str, max 200 chars, professional response),\n"
                f"  sentiment (one of: positive/neutral/negative/angry).\n\n"
                f"Platform: {msg.platform}\nMessage: {msg.body or ''}",
                res_model=self._name,
                res_id=msg.id,
            )
            if result["ok"]:
                content = result["content"]
                reply_text = content[:200]
                sentiment = None
                try:
                    clean = content.strip()
                    if clean.startswith("```"):
                        clean = clean.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean)
                    reply_text = (data.get("reply") or content)[:200]
                    raw_sent = data.get("sentiment", "")
                    if raw_sent in self._VALID_SENTIMENTS:
                        sentiment = raw_sent
                except (json.JSONDecodeError, ValueError):
                    pass
                vals = {
                    "ai_draft_reply": reply_text,
                    "ai_final_reply": reply_text,
                    "state": "pending",
                }
                if sentiment:
                    vals["sentiment"] = sentiment
                msg.write(vals)

    def action_approve_and_send(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError("Reply must be approved before sending.")
        _logger.info(
            "[SOCIAL MOCK] Reply to %s on %s: %s",
            self.author_name,
            self.platform,
            self.ai_final_reply,
        )
        self.state = "sent"

    def action_approve(self):
        self.write({"state": "approved"})

    def action_reject(self):
        self.write({"state": "new"})

    def action_escalate(self):
        self.write({"state": "escalated"})

    def action_archive(self):
        self.write({"state": "archived"})

    def action_create_lead(self):
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
                "name": f"Social: {self.author_name or self.platform}",
                "type": "lead",
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
        """Create helpdesk ticket from this social message."""
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
                "name": f"Social {self.message_type}: {self.author_name or self.platform}",
                "description": self.body or "",
                "source": "social",
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
