"""Ollama local provider — privacy-first, no external calls."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import BaseProvider, ChatMessage, ChatResponse, EmbedResponse

_DEFAULT_MODEL = "llama3.2"
_DEFAULT_EMBED = "nomic-embed-text"


class OllamaProvider(BaseProvider):
    name = "ollama"
    is_external = False  # local — safe for payroll/financial content

    def __init__(self, base_url: str = "http://localhost:11434", model: str = _DEFAULT_MODEL):
        self._base_url = base_url.rstrip("/")
        self._model = model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system: str = "",
    ) -> ChatResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        body = {
            "model": model or self._model,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        content = data.get("message", {}).get("content", "")
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="ollama",
            finish_reason=data.get("done_reason", "stop"),
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system: str = "",
    ) -> AsyncIterator[str]:
        import json

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        body = {
            "model": model or self._model,
            "messages": msgs,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    delta = event.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if event.get("done"):
                        break

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
    async def embed(self, text: str, *, model: str = "") -> EmbedResponse:
        body = {"model": model or _DEFAULT_EMBED, "prompt": text}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base_url}/api/embeddings", json=body)
            resp.raise_for_status()
            data = resp.json()
        return EmbedResponse(
            embedding=data["embedding"],
            model=model or _DEFAULT_EMBED,
            provider="ollama",
        )
