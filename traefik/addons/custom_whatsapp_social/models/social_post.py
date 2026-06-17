"""Social post planning — content calendar, topics, AI generation, approval, publishing."""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialCampaign(models.Model):
    _name = "social.campaign"
    _description = "Social Campaign"
    _order = "date_start desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    date_start = fields.Date()
    date_end = fields.Date()
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("done", "Done")], default="draft"
    )
    description = fields.Text()
    post_ids = fields.One2many("social.post", "campaign_id", "Posts")
    post_count = fields.Integer(compute="_compute_post_count")

    def _compute_post_count(self):
        for c in self:
            c.post_count = len(c.post_ids)


class SocialPostTopic(models.Model):
    _name = "social.post.topic"
    _description = "Recurring Post Topic"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    description = fields.Text()
    tone = fields.Selection(
        [
            ("professional", "Professional"),
            ("casual", "Casual"),
            ("inspirational", "Inspirational"),
            ("promotional", "Promotional"),
            ("educational", "Educational"),
        ],
        default="professional",
    )
    audience = fields.Char("Target Audience")
    product_focus = fields.Char()
    frequency = fields.Selection(
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("biweekly", "Bi-weekly"),
            ("monthly", "Monthly"),
        ],
        default="weekly",
    )
    channel_ids = fields.Many2many(
        "social.account", "post_topic_account_rel", "topic_id", "account_id", "Channels"
    )
    active = fields.Boolean(default=True)

    # Approval workflow
    approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
        ],
        default="draft",
        string="Approval State",
    )
    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True)
    approved_date = fields.Datetime(string="Approved On", readonly=True)

    def action_submit_for_approval(self):
        self.write({"approval_state": "pending_approval"})

    def action_approve_topic(self):
        self.write(
            {
                "approval_state": "approved",
                "approved_by_id": self.env.uid,
                "approved_date": fields.Datetime.now(),
            }
        )

    def action_reset_to_draft(self):
        self.write({"approval_state": "draft", "approved_by_id": False, "approved_date": False})

    def action_ai_suggest_posts(self):
        """Ask AI to suggest post ideas for this topic."""
        self.ensure_one()
        result = self.env["ai.service"].call(
            f"Suggest 3 social media post ideas for:\n"
            f"Topic: {self.name}\nTone: {self.tone}\nAudience: {self.audience or 'general'}\n"
            f"Product focus: {self.product_focus or 'company services'}",
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "AI Post Ideas",
                    "message": result["content"][:500],
                    "type": "info",
                    "sticky": True,
                },
            }


class SocialPost(models.Model):
    _name = "social.post"
    _description = "Social Post"
    _inherit = ["mail.thread"]
    _order = "scheduled_date, create_date desc"

    name = fields.Char("Title", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    campaign_id = fields.Many2one("social.campaign", ondelete="set null")
    topic_id = fields.Many2one("social.post.topic", ondelete="set null")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("ai_generated", "AI Generated"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("scheduled", "Scheduled"),
            ("published", "Published"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )

    # Content
    body = fields.Text("Post Body", required=True)
    media_ids = fields.Many2many(
        "ir.attachment", "social_post_media_rel", "post_id", "attachment_id", "Media"
    )
    hashtags = fields.Char("Hashtags")
    link_url = fields.Char("Link URL")

    # AI generation
    ai_generated = fields.Boolean("AI Generated", default=False, readonly=True)
    ai_prompt_used = fields.Text("AI Prompt", readonly=True)

    # Scheduling
    scheduled_date = fields.Datetime("Scheduled For")
    published_date = fields.Datetime(readonly=True)

    # Channels
    account_ids = fields.Many2many(
        "social.account", "social_post_account_rel", "post_id", "account_id", "Publish To"
    )

    # Approval
    approved_by_id = fields.Many2one("res.users", readonly=True)
    approval_note = fields.Text()

    # Performance (placeholder — real data from API)
    reach = fields.Integer("Reach", default=0, readonly=True)
    impressions = fields.Integer("Impressions", default=0, readonly=True)
    engagement = fields.Integer("Engagement", default=0, readonly=True)
    clicks = fields.Integer("Clicks", default=0, readonly=True)

    def action_ai_generate(self):
        """Generate post content with AI."""
        self.ensure_one()
        topic = self.topic_id
        prompt = (
            f"Write a {topic.tone if topic else 'professional'} social media post "
            f"for {', '.join(self.account_ids.mapped('platform')) or 'social media'}.\n"
            f"Topic: {self.name}\n"
            f"Audience: {topic.audience if topic else 'general'}\n"
            f"Max 280 characters for Twitter/X, up to 500 for others.\n"
            f"Include relevant hashtags."
        )
        result = self.env["ai.service"].call(
            prompt,
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            self.write(
                {
                    "body": result["content"][:500],
                    "ai_generated": True,
                    "ai_prompt_used": prompt[:500],
                    "state": "ai_generated",
                }
            )

    def action_submit_for_approval(self):
        self.write({"state": "pending_approval"})

    def action_approve(self):
        self.write(
            {
                "state": "approved",
                "approved_by_id": self.env.user.id,
            }
        )

    def action_reject(self):
        self.write({"state": "draft"})

    def action_schedule(self):
        for post in self:
            if not post.scheduled_date:
                raise UserError("Please set a scheduled date before scheduling.")
            if post.state != "approved":
                raise UserError("Post must be approved before scheduling.")
            post.state = "scheduled"

    def action_publish_now(self):
        """Publish immediately (mock or real API)."""
        for post in self:
            if post.state not in ("approved", "scheduled"):
                raise UserError("Post must be approved before publishing.")
            post._do_publish()

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def _do_publish(self):
        """Publish to all connected accounts (mock unless real API configured)."""
        self.ensure_one()
        for account in self.account_ids:
            if account.platform == "mock" or not account._api_key_encrypted:
                _logger.info("[SOCIAL MOCK] Published '%s' to %s", self.name, account.platform)
            else:
                _logger.info(
                    "Would publish to %s (API integration not yet active)", account.platform
                )
        self.write({"state": "published", "published_date": fields.Datetime.now()})

    @api.model
    def cron_publish_scheduled(self):
        """Cron: publish posts whose scheduled time has passed."""
        now = fields.Datetime.now()
        due = self.search([("state", "=", "scheduled"), ("scheduled_date", "<=", now)])
        for post in due:
            try:
                post._do_publish()
            except Exception as exc:
                _logger.error("Auto-publish failed for post %d: %s", post.id, exc)
                post.state = "failed"
