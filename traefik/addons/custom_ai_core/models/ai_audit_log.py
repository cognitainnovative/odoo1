"""Immutable AI audit log — records every AI call for traceability."""

import hashlib
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiAuditLog(models.Model):
    _name = "ai.audit.log"
    _description = "AI Audit Log"
    _order = "create_date desc"
    _log_access = True

    company_id = fields.Many2one("res.company", index=True, default=lambda s: s.env.company)
    user_id = fields.Many2one("res.users", index=True, default=lambda s: s.env.user)
    provider_id = fields.Many2one("ai.provider", ondelete="set null")
    prompt_template_id = fields.Many2one("ai.prompt.template", ondelete="set null")

    model_used = fields.Char(readonly=True)
    provider_code = fields.Char(readonly=True)

    # Token / performance metrics
    input_tokens = fields.Integer(readonly=True)
    output_tokens = fields.Integer(readonly=True)
    latency_ms = fields.Integer("Latency (ms)", readonly=True)

    # Status
    status = fields.Selection(
        [("success", "Success"), ("error", "Error"), ("redacted", "Redacted (no call made)")],
        default="success",
        readonly=True,
    )
    was_redacted = fields.Boolean("PII Was Redacted", readonly=True)
    error_message = fields.Text(readonly=True)

    # Content fingerprints (not the full content — privacy)
    input_hash = fields.Char("Input SHA-256 (first 512 chars)", readonly=True)
    output_preview = fields.Text("Output Preview (first 200 chars)", readonly=True)

    # Context reference
    res_model = fields.Char("Related Model", readonly=True)
    res_id = fields.Integer("Related Record ID", readonly=True)

    @api.model
    def log(
        self,
        *,
        provider=None,
        prompt_template=None,
        model_used: str = "",
        provider_code: str = "",
        input_text: str = "",
        output_text: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        status: str = "success",
        was_redacted: bool = False,
        error_message: str = "",
        res_model: str = "",
        res_id: int = 0,
    ) -> "AiAuditLog":
        """Create an immutable audit log entry."""
        input_preview = input_text[:512] if input_text else ""
        record = self.sudo().create(
            {
                "company_id": self.env.company.id,
                "user_id": self.env.user.id,
                "provider_id": provider.id if provider else False,
                "prompt_template_id": prompt_template.id if prompt_template else False,
                "model_used": model_used,
                "provider_code": provider_code,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
                "status": status,
                "was_redacted": was_redacted,
                "error_message": error_message[:2000] if error_message else "",
                "input_hash": (
                    hashlib.sha256(input_preview.encode()).hexdigest() if input_preview else ""
                ),
                "output_preview": output_text[:200] if output_text else "",
                "res_model": res_model,
                "res_id": res_id,
            }
        )
        # Mirror significant events to central platform audit log
        if status == "error" or (provider_code and provider_code != "mock"):
            try:
                self.env["platform.audit.log"].sudo().log(
                    "ai_output",
                    res_model=res_model or self._name,
                    res_id=res_id or False,
                    res_name=model_used,
                    summary=(
                        f"AI call via '{provider_code}' model='{model_used}' "
                        f"status={status} tokens={input_tokens}+{output_tokens}"
                    ),
                    details={
                        "provider_code": provider_code,
                        "model_used": model_used,
                        "status": status,
                        "was_redacted": was_redacted,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                    severity="critical" if status == "error" else "info",
                )
            except Exception:
                _logger.debug("platform.audit.log not available yet — ai event not mirrored")
        return record

    def write(self, vals):
        raise UserError("AI audit log records are immutable and cannot be modified.")

    def unlink(self):
        raise UserError("AI audit log records cannot be deleted.")
