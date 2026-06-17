"""User correction-learning store — captures AI draft edits for quality improvement."""

from odoo import fields, models


class AiFeedback(models.Model):
    _name = "ai.feedback"
    _description = "AI Response Feedback"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    audit_log_id = fields.Many2one("ai.audit.log", "AI Audit Entry", ondelete="set null")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)
    user_id = fields.Many2one("res.users", default=lambda s: s.env.user)

    # What the AI said vs what the human actually sent
    original_draft = fields.Text("AI Draft", readonly=True)
    final_reply = fields.Text("Final Reply Sent")
    was_edited = fields.Boolean("Human Edited", compute="_compute_was_edited", store=True)

    # Classification
    edit_reason = fields.Selection(
        [
            ("factually_wrong", "Factually Wrong"),
            ("wrong_tone", "Wrong Tone / Style"),
            ("missing_info", "Missing Information"),
            ("too_long", "Too Long"),
            ("too_short", "Too Short"),
            ("hallucination", "Hallucination"),
            ("policy_violation", "Policy / Compliance Issue"),
            ("other", "Other"),
        ],
        string="Reason for Edit",
    )
    category = fields.Selection(
        [
            ("crm", "CRM"),
            ("helpdesk", "Helpdesk"),
            ("email", "Email"),
            ("general", "General"),
        ],
        default="general",
    )
    knowledge_source = fields.Char(
        "Knowledge Source Used", help="Which RAG document or prompt template was used."
    )

    # Learning loop
    add_to_kb = fields.Boolean(
        "Add Final Reply to Knowledge Base",
        help="If checked, the final reply will be proposed as a new KB article after approval.",
    )
    approval_status = fields.Selection(
        [("pending", "Pending Review"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="pending",
        tracking=True,
    )
    approver_id = fields.Many2one("res.users", "Approved / Rejected By")
    notes = fields.Text()

    def _compute_was_edited(self):
        for rec in self:
            rec.was_edited = bool(rec.final_reply and rec.final_reply != rec.original_draft)

    def action_approve(self):
        self.write({"approval_status": "approved", "approver_id": self.env.user.id})

    def action_reject(self):
        self.write({"approval_status": "rejected", "approver_id": self.env.user.id})
