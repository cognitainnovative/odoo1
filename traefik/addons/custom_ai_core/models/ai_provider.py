"""AI provider configuration — per-company LLM settings with encrypted keys."""

import os

from cryptography.fernet import Fernet, InvalidToken
from odoo import api, fields, models
from odoo.exceptions import UserError


def _get_fernet() -> Fernet:
    key = os.environ.get("APP_SECRET_ENCRYPTION_KEY", "")
    if key:
        try:
            return Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            pass
    # Dev fallback: hardcoded key for local development only.
    # WARNING: replace with a proper key via APP_SECRET_ENCRYPTION_KEY in production.
    dev_key = b"EQIRySotqyuQKgivvmjaGP2al_5cPPPR_nCezg1yuzQ="
    return Fernet(dev_key)


class AiProvider(models.Model):
    _name = "ai.provider"
    _description = "AI Provider Configuration"
    _order = "sequence, name"
    _rec_name = "name"

    name = fields.Char(required=True)
    code = fields.Selection(
        [
            ("mock", "Mock (Testing / CI)"),
            ("anthropic", "Anthropic — Claude"),
            ("openai", "OpenAI-compatible"),
            ("azure", "Azure OpenAI (placeholder — requires endpoint + api-version)"),
            ("ollama", "Ollama (Local, no data egress)"),
        ],
        required=True,
        default="mock",
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )

    # API / connection
    base_url = fields.Char("Base URL / Endpoint", help="Leave blank for provider default.")
    _api_key_encrypted = fields.Char("Encrypted API Key", copy=False)
    api_key = fields.Char(
        "API Key",
        compute="_compute_api_key",
        inverse="_inverse_api_key",
        store=False,
        copy=False,
    )

    # Model settings
    model_name = fields.Char("Model")
    embedding_model = fields.Char("Embedding Model")
    temperature = fields.Float(default=0.7, digits=(4, 2))
    max_tokens = fields.Integer("Max Output Tokens", default=2048)

    # Privacy / security
    allow_external = fields.Boolean(
        "Allow External Calls",
        default=False,
        help="When disabled, external API calls are blocked for this provider.",
    )
    privacy_mode = fields.Boolean(
        "Privacy Mode (Redact PII)",
        default=True,
        help="Redact PII patterns from input before sending to this provider.",
    )

    is_active = fields.Boolean(default=True)
    notes = fields.Text()

    _provider_company_code_uniq = models.Constraint(
        "UNIQUE(company_id, code)",
        "Only one provider per code per company.",
    )

    # ── Key encryption ─────────────────────────────────────────────────────────

    @api.depends("_api_key_encrypted")
    def _compute_api_key(self):
        fernet = _get_fernet()
        for rec in self:
            encrypted = rec._api_key_encrypted
            if encrypted:
                try:
                    rec.api_key = fernet.decrypt(encrypted.encode()).decode()
                except (InvalidToken, Exception):
                    rec.api_key = ""
            else:
                rec.api_key = ""

    def _inverse_api_key(self):
        fernet = _get_fernet()
        for rec in self:
            if rec.api_key:
                rec._api_key_encrypted = fernet.encrypt(rec.api_key.encode()).decode()
            else:
                rec._api_key_encrypted = ""

    # ── Provider factory ───────────────────────────────────────────────────────

    def get_provider_instance(self):
        """Return a lib.providers.BaseProvider instance for this config record."""
        self.ensure_one()
        from ..lib.providers import get_provider

        if not self.allow_external and self.code not in ("mock", "ollama"):
            raise UserError(
                f"Provider '{self.name}' does not allow external calls. "
                "Enable 'Allow External Calls' or use Ollama/Mock."
            )
        return get_provider(
            code=self.code,
            api_key=self.api_key or "",
            base_url=self.base_url or "",
            model=self.model_name or "",
        )

    @api.model
    def get_default_provider(self, prefer_code: str | None = None):
        """Return the active provider for the current company.

        Falls back to mock if nothing is configured.
        """
        domain = [("company_id", "=", self.env.company.id), ("is_active", "=", True)]
        if prefer_code:
            provider = self.search(domain + [("code", "=", prefer_code)], limit=1)
            if provider:
                return provider
        provider = self.search(domain, order="sequence", limit=1)
        if not provider:
            # Return a transient mock provider that is not persisted
            return self.new({"name": "Auto Mock", "code": "mock", "allow_external": False})
        return provider

    def action_test_connection(self):
        """Test the provider connection and show a notification."""
        self.ensure_one()
        from ..lib.providers import AiMessage

        try:
            instance = self.get_provider_instance()
            resp = instance.call([AiMessage(role="user", content="Reply with: OK")])
            if resp.ok:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Connection OK",
                        "message": f"Provider '{self.name}' responded: {resp.content[:100]}",
                        "type": "success",
                    },
                }
            raise UserError(f"Provider returned error: {resp.error}")
        except UserError:
            raise
        except Exception as exc:
            raise UserError(f"Connection failed: {exc}") from exc
