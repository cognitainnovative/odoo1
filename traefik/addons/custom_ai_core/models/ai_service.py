"""Central AI service — the main entry point for all AI calls from other addons."""

import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiService(models.AbstractModel):
    """Abstract model: call self.env['ai.service'].call(...) from any other addon."""

    _name = "ai.service"
    _description = "AI Service (call dispatch)"

    @api.model
    def call(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        template_code: str | None = None,
        template_vars: dict | None = None,
        provider_code: str | None = None,
        res_model: str = "",
        res_id: int = 0,
    ) -> dict:
        """Make an AI call and return a result dict.

        Returns:
            {
                "ok": bool,
                "content": str,
                "was_redacted": bool,
                "provider": str,
                "model": str,
                "audit_log_id": int,
                "error": str,
            }
        """
        from ..lib.providers import AiMessage
        from ..lib.redaction import redact

        # --- 1. Resolve provider ---
        provider_rec = self.env["ai.provider"].get_default_provider(prefer_code=provider_code)

        # --- 2. Build messages ---
        if template_code:
            tmpl = self.env["ai.prompt.template"].get_template(template_code)
            if tmpl:
                sys_tmpl, user_tmpl = tmpl.render(template_vars or {})
                system_prompt = system_prompt or sys_tmpl
                user_prompt = user_tmpl or user_prompt
            else:
                _logger.warning("AI template '%s' not found — using raw prompt", template_code)

        # --- 3. Redact PII if privacy mode is on ---
        was_redacted = False
        if provider_rec.privacy_mode:
            user_prompt, was_redacted_u = redact(user_prompt)
            if system_prompt:
                system_prompt, was_redacted_s = redact(system_prompt)
                was_redacted = was_redacted_u or was_redacted_s
            else:
                was_redacted = was_redacted_u

        messages = []
        if system_prompt:
            messages.append(AiMessage(role="system", content=system_prompt))
        messages.append(AiMessage(role="user", content=user_prompt))

        # --- 4. Call provider ---
        try:
            instance = provider_rec.get_provider_instance()
            resp = instance.call(
                messages,
                model=provider_rec.model_name or "",
                temperature=provider_rec.temperature,
                max_tokens=provider_rec.max_tokens,
            )
        except UserError:
            raise
        except Exception as exc:
            _logger.error("AI call failed: %s", exc)
            resp_obj = type(
                "R",
                (),
                {
                    "ok": False,
                    "error": str(exc),
                    "content": "",
                    "model": "",
                    "provider": "",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_ms": 0,
                },
            )()
            resp = resp_obj

        # --- 5. Audit log ---
        call_ok = getattr(resp, "ok", False)
        if not call_ok:
            status = "error"
        elif was_redacted:
            status = "redacted"
        else:
            status = "success"

        audit = self.env["ai.audit.log"].log(
            provider=provider_rec if provider_rec.id else None,
            model_used=getattr(resp, "model", ""),
            provider_code=getattr(resp, "provider", provider_rec.code),
            input_text=user_prompt,
            output_text=getattr(resp, "content", ""),
            input_tokens=getattr(resp, "input_tokens", 0),
            output_tokens=getattr(resp, "output_tokens", 0),
            latency_ms=getattr(resp, "latency_ms", 0),
            status=status,
            was_redacted=was_redacted,
            error_message=getattr(resp, "error", ""),
            res_model=res_model,
            res_id=res_id,
        )

        return {
            "ok": getattr(resp, "ok", False),
            "content": getattr(resp, "content", ""),
            "was_redacted": was_redacted,
            "provider": getattr(resp, "provider", provider_rec.code),
            "model": getattr(resp, "model", ""),
            "audit_log_id": audit.id,
            "error": getattr(resp, "error", ""),
        }

    @api.model
    def rag_search(
        self,
        query: str,
        limit: int = 5,
        company_id: int | None = None,
    ) -> list[dict]:
        """Search the RAG knowledge base and return cited chunks."""
        return self.env["ai.document.chunk"].search_similar(
            query=query,
            company_id=company_id or self.env.company.id,
            limit=limit,
        )

    @api.model
    def call_with_rag(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        rag_limit: int = 3,
        **kwargs,
    ) -> dict:
        """RAG-augmented call: retrieve relevant chunks, inject as context, then call AI."""
        chunks = self.rag_search(user_prompt, limit=rag_limit)

        context_text = ""
        citations = []
        if chunks:
            context_parts = []
            for i, chunk in enumerate(chunks, 1):
                context_parts.append(f"[{i}] Source: {chunk['source']}\n{chunk['content']}")
                citations.append(
                    {"index": i, "source": chunk["source"], "confidence": chunk["confidence"]}
                )
            context_text = "\n\n".join(context_parts)

        if context_text:
            rag_system = (
                "You are a helpful assistant. Use the following knowledge base excerpts to answer "
                "the question. Always cite your sources using [number] notation.\n\n"
                f"Knowledge Base:\n{context_text}"
            )
            system_prompt = f"{rag_system}\n\n{system_prompt}" if system_prompt else rag_system

        result = self.call(user_prompt, system_prompt=system_prompt, **kwargs)
        result["citations"] = citations
        return result
