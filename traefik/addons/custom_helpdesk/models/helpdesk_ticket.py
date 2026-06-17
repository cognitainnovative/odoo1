"""Helpdesk ticket — core model with AI classification, SLA, approval workflow, smart routing."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _description = "Helpdesk Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, sla_deadline, create_date desc"

    name = fields.Char("Subject", required=True, tracking=True)
    description = fields.Html("Description")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)

    # People
    partner_id = fields.Many2one("res.partner", "Customer", index=True)
    user_id = fields.Many2one("res.users", "Assigned To", index=True, tracking=True)
    team_id = fields.Many2one("helpdesk.team", "Team", tracking=True)

    # Classification
    stage_id = fields.Many2one(
        "helpdesk.stage",
        "Stage",
        default=lambda s: s.env["helpdesk.stage"].search([], order="sequence", limit=1),
        tracking=True,
        index=True,
    )
    priority = fields.Selection(
        [("0", "Normal"), ("1", "High"), ("2", "Urgent"), ("3", "Critical")],
        default="0",
        tracking=True,
    )
    category = fields.Selection(
        [
            ("billing", "Billing"),
            ("technical", "Technical"),
            ("product", "Product / Service"),
            ("complaint", "Complaint"),
            ("general", "General Inquiry"),
            ("other", "Other"),
        ],
        default="general",
    )
    source = fields.Selection(
        [
            ("email", "Email"),
            ("chat", "Chat"),
            ("whatsapp", "WhatsApp"),
            ("social", "Social Media"),
            ("phone", "Phone"),
            ("manual", "Manual"),
            ("portal", "Customer Portal"),
        ],
        default="manual",
    )
    language_code = fields.Char("Language", default="en")

    # Routing — skill and product
    skill_id = fields.Many2one("helpdesk.skill", "Required Skill", index=True, ondelete="set null")
    product_id = fields.Many2one(
        "product.product", "Related Product", index=True, ondelete="set null"
    )

    # SLA
    sla_id = fields.Many2one("helpdesk.sla", "SLA Policy")
    sla_deadline = fields.Datetime("SLA Deadline", compute="_compute_sla_deadline", store=True)
    sla_breached = fields.Boolean("SLA Breached", compute="_compute_sla_breached", store=False)

    # AI classification + draft reply
    ai_category = fields.Char("AI-Suggested Category", readonly=True)
    ai_priority = fields.Selection(
        [("0", "Normal"), ("1", "High"), ("2", "Urgent"), ("3", "Critical")],
        string="AI-Suggested Priority",
        readonly=True,
    )
    ai_sentiment = fields.Selection(
        [
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("frustrated", "Frustrated"),
            ("angry", "Angry"),
            ("urgent", "Urgent"),
        ],
        string="Sentiment",
        readonly=True,
    )
    ai_summary = fields.Text("AI Summary", readonly=True)
    ai_draft_reply = fields.Text("AI Draft Reply", readonly=True)
    ai_approval_state = fields.Selection(
        [
            ("none", "No Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved — Ready to Send"),
            ("rejected", "Rejected"),
            ("needs_info", "Needs More Information"),
            ("sent", "Sent"),
        ],
        string="Reply Approval",
        default="none",
        tracking=True,
    )
    ai_edit_reason = fields.Text("Edit Reason")
    ai_final_reply = fields.Text("Final Reply (edited)")

    # AI suggested assignee (set by smart routing after classification)
    ai_suggested_user_id = fields.Many2one(
        "res.users", "AI-Suggested Assignee", readonly=True, ondelete="set null"
    )

    # Linked records
    sale_order_id = fields.Many2one("sale.order", "Linked Order", ondelete="set null")
    invoice_id = fields.Many2one("account.move", "Linked Invoice", ondelete="set null")
    lead_id = fields.Many2one("crm.lead", "Linked Deal", ondelete="set null")

    # Internal note
    internal_note = fields.Text("Internal Notes")

    # Risk flags
    is_complaint = fields.Boolean("Complaint Detected", readonly=True)
    has_legal_risk = fields.Boolean("Legal Risk Detected", readonly=True)
    has_missing_info = fields.Boolean("Missing Info", readonly=True)

    # ── SLA computed ──────────────────────────────────────────────────────────

    @api.depends("sla_id", "create_date")
    def _compute_sla_deadline(self):
        for ticket in self:
            if ticket.sla_id and ticket.create_date:
                ticket.sla_deadline = ticket.sla_id.get_deadline(ticket.create_date)
            else:
                ticket.sla_deadline = False

    @api.depends("sla_deadline", "stage_id.is_closed")
    def _compute_sla_breached(self):
        now = fields.Datetime.now()
        for ticket in self:
            if ticket.sla_deadline and not ticket.stage_id.is_closed:
                ticket.sla_breached = ticket.sla_deadline < now
            else:
                ticket.sla_breached = False

    # ── AI actions ────────────────────────────────────────────────────────────

    def action_ai_classify(self):
        """Classify ticket: category, priority, sentiment, risk flags, skill needed.

        After classification the ticket is also auto-routed (assignee suggestion
        via workload-balanced skill matching) and a follow-up activity is scheduled
        when the AI detects missing information.
        """
        for ticket in self:
            product_ctx = (
                f"Related product: {ticket.product_id.name}\n" if ticket.product_id else ""
            )
            prompt = (
                f"Classify this helpdesk ticket. Return JSON only with keys: "
                f"category (billing/technical/product/complaint/general/other), "
                f"priority (0=normal/1=high/2=urgent), "
                f"sentiment (positive/neutral/frustrated/angry/urgent), "
                f"skill_needed (short free-text skill name, e.g. 'billing', 'network', 'refund' — "
                f"or empty string if none), "
                f"is_complaint (true/false), has_legal_risk (true/false), "
                f"has_missing_info (true/false), summary (one sentence).\n\n"
                f"Subject: {ticket.name}\n"
                f"{product_ctx}"
                f"Description: {ticket.description or ''}"
            )
            result = self.env["ai.service"].call(prompt, res_model=self._name, res_id=ticket.id)
            if result["ok"]:
                import json

                try:
                    clean = result["content"].strip()
                    if clean.startswith("```"):
                        parts = clean.split("```")
                        clean = parts[1].lstrip("json").strip() if len(parts) > 1 else clean
                    data = json.loads(clean)
                    ticket.write(
                        {
                            "ai_category": data.get("category", ""),
                            "ai_priority": str(data.get("priority", "0")),
                            "ai_sentiment": data.get("sentiment", "neutral"),
                            "ai_summary": data.get("summary", ""),
                            "is_complaint": bool(data.get("is_complaint")),
                            "has_legal_risk": bool(data.get("has_legal_risk")),
                            "has_missing_info": bool(data.get("has_missing_info")),
                        }
                    )
                    # Match AI-suggested skill name to a helpdesk.skill record
                    skill_name = (data.get("skill_needed") or "").strip()
                    if skill_name and not ticket.skill_id:
                        skill = self.env["helpdesk.skill"].search(
                            [("name", "ilike", skill_name)], limit=1
                        )
                        if skill:
                            ticket.skill_id = skill

                    # Smart-route: suggest assignee via workload + skill
                    ticket._suggest_assignee()

                    # Auto-schedule follow-up if missing info detected
                    if ticket.has_missing_info:
                        ticket._schedule_missing_info_followup()

                except (json.JSONDecodeError, ValueError) as e:
                    _logger.warning("Ticket classification JSON parse failed: %s", e)

    def _suggest_assignee(self):
        """Populate ai_suggested_user_id using workload-balanced, skill-aware routing.

        Passes priority and sla_deadline so that urgent / SLA-at-risk tickets
        are routed to the lowest-load agent regardless of skill constraints.
        """
        self.ensure_one()
        if not self.team_id:
            return
        suggested = self.team_id._get_next_assignee(
            skill_id=self.skill_id.id if self.skill_id else None,
            priority=self.priority,
            sla_deadline=self.sla_deadline,
        )
        if suggested:
            self.ai_suggested_user_id = suggested

    def action_accept_ai_assignee(self):
        """Apply the AI-suggested assignee to the ticket."""
        for ticket in self:
            if ticket.ai_suggested_user_id:
                ticket.user_id = ticket.ai_suggested_user_id

    def _auto_route(self):
        """Auto-assign team and agent based on skill + workload when auto_assign is on.

        Passes priority and sla_deadline so that urgent / SLA-at-risk tickets
        bypass normal filtering and always land on the lowest-load agent.
        """
        for ticket in self:
            if ticket.user_id or not ticket.team_id:
                continue
            if ticket.team_id.auto_assign:
                assignee = ticket.team_id._get_next_assignee(
                    skill_id=ticket.skill_id.id if ticket.skill_id else None,
                    priority=ticket.priority,
                    sla_deadline=ticket.sla_deadline,
                )
                if assignee:
                    ticket.user_id = assignee

    def _schedule_missing_info_followup(self):
        """Schedule a follow-up activity to request missing information from customer."""
        self.ensure_one()
        existing = self.env["mail.activity"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("activity_type_id", "=", self.env.ref("mail.mail_activity_data_todo").id),
            ],
            limit=1,
        )
        if not existing:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                note=(
                    f"AI detected missing information in ticket '{self.name}'. "
                    "Please follow up with the customer to obtain the required details."
                ),
                user_id=(self.user_id or self.env.user).id,
            )

    def action_ai_draft_reply(self):
        """Generate an AI draft reply — sets state to pending approval."""
        for ticket in self:
            context = ""
            if ticket.ai_summary:
                context = f"Issue summary: {ticket.ai_summary}\n"
            prompt = (
                f"Draft a professional, empathetic helpdesk reply for this ticket.\n"
                f"Subject: {ticket.name}\n"
                f"{context}"
                f"Category: {ticket.category}\nSentiment: {ticket.ai_sentiment or 'neutral'}\n"
                f"Description: {ticket.description or ''}"
            )
            result = self.env["ai.service"].call(
                prompt,
                template_code="helpdesk_reply_draft",
                template_vars={
                    "ticket_text": ticket.name,
                    "category": ticket.category or "general",
                    "context": context,
                },
                res_model=self._name,
                res_id=ticket.id,
            )
            if result["ok"]:
                ticket.write(
                    {
                        "ai_draft_reply": result["content"],
                        "ai_final_reply": result["content"],
                        "ai_approval_state": "pending",
                    }
                )

    def action_approve_reply(self):
        self.write({"ai_approval_state": "approved"})

    def action_reject_reply(self):
        self.write({"ai_approval_state": "rejected"})

    def action_needs_info(self):
        self.write({"ai_approval_state": "needs_info"})

    def action_send_reply(self):
        """Send the approved reply to the customer."""
        for ticket in self:
            if ticket.ai_approval_state != "approved":
                raise UserError(
                    "Reply must be approved before sending. "
                    "AI replies are NEVER auto-sent without human approval."
                )
            if not ticket.partner_id:
                raise UserError("No customer linked to send reply to.")

            final = ticket.ai_final_reply or ticket.ai_draft_reply
            ticket.message_post(
                body=final,
                subtype_id=self.env.ref("mail.mt_comment").id,
                partner_ids=ticket.partner_id.ids,
            )
            ticket.ai_approval_state = "sent"

            # Store edit reason for learning loop
            if ticket.ai_edit_reason:
                self.env["ai.feedback"].create(
                    {
                        "company_id": ticket.company_id.id,
                        "original_draft": ticket.ai_draft_reply,
                        "final_reply": ticket.ai_final_reply,
                        "edit_reason": "wrong_tone",
                        "category": "helpdesk",
                        "notes": ticket.ai_edit_reason,
                        "add_to_kb": False,
                    }
                )

    def action_close(self):
        closed_stage = self.env["helpdesk.stage"].search(
            [("is_closed", "=", True)], order="sequence desc", limit=1
        )
        if closed_stage:
            self.stage_id = closed_stage

    def action_follow_up(self):
        """Schedule a follow-up activity for this ticket."""
        for ticket in self:
            ticket.activity_schedule(
                "mail.mail_activity_data_todo",
                note=f"Follow-up required on ticket: {ticket.name}",
                user_id=(ticket.user_id or self.env.user).id,
            )

    def action_knowledge_suggest(self):
        """Return knowledge documents ranked by relevance to this ticket.

        Searches ai.document records whose title or tags match the ticket's
        subject keywords, then falls back to category-filtered results.
        """
        self.ensure_one()
        # Build keyword list from subject words (3+ chars, deduped)
        keywords = list({w for w in self.name.split() if len(w) >= 3})

        domain = [("state", "=", "active")]
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))

        # Try to find semantically relevant documents via keyword search
        matching_ids = []
        for kw in keywords[:5]:
            docs = self.env["ai.document"].search(
                domain + ["|", ("name", "ilike", kw), ("tags", "ilike", kw)],
                limit=10,
            )
            matching_ids.extend(docs.ids)

        # Deduplicate while preserving relevance order
        seen = set()
        ordered_ids = [i for i in matching_ids if not (i in seen or seen.add(i))]

        if not ordered_ids:
            # Fall back to category filter
            return {
                "type": "ir.actions.act_window",
                "name": f"Knowledge Base — {self.name[:60]}",
                "res_model": "ai.document",
                "view_mode": "list,form",
                "domain": domain,
                "context": {"search_default_category": self.category or ""},
            }

        return {
            "type": "ir.actions.act_window",
            "name": f"Knowledge Base — {self.name[:60]}",
            "res_model": "ai.document",
            "view_mode": "list,form",
            "domain": [("id", "in", ordered_ids)],
        }

    @api.model
    def cron_check_sla(self):
        """Cron: warn on approaching SLA and post a note on breached tickets."""
        from datetime import datetime, timedelta

        now = datetime.now()
        warning_cutoff = now + timedelta(hours=4)

        # Already breached
        breaching = self.search([("sla_deadline", "<", now), ("stage_id.is_closed", "=", False)])
        for ticket in breaching:
            ticket.message_post(
                body=f"⚠️ SLA breached! Deadline was {ticket.sla_deadline}.",
                subtype_id=self.env.ref("mail.mt_note").id,
            )

        # Approaching breach (within 4 hours, not yet breached)
        approaching = self.search(
            [
                ("sla_deadline", ">=", now),
                ("sla_deadline", "<=", warning_cutoff),
                ("stage_id.is_closed", "=", False),
            ]
        )
        for ticket in approaching:
            ticket.message_post(
                body=(
                    f"⏰ SLA warning: deadline approaching in less than 4 hours "
                    f"({ticket.sla_deadline})."
                ),
                subtype_id=self.env.ref("mail.mt_note").id,
            )
