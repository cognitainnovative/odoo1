"""Anthropic Claude provider (Messages API)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import BaseProvider, ChatMessage, ChatResponse, EmbedResponse

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_EMBED_NOT_SUPPORTED = "Anthropic does not provide an embeddings API. Use ollama or openai."


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    is_external = True

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL):
        self._api_key = api_key
        self._model = model
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_body(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        system: str,
    ) -> dict:
        body: dict = {
            "model": model or self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages if m.role != "system"
            ],
        }
        sys_content = system or next((m.content for m in messages if m.role == "system"), "")
        if sys_content:
            body["system"] = sys_content
        return body

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system: str = "",
    ) -> ChatResponse:
        body = self._build_body(messages, model, temperature, max_tokens, system)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(_API_URL, headers=self._headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        content = data["content"][0]["text"] if data.get("content") else ""
        usage = data.get("usage", {})
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            provider="anthropic",
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason", "stop"),
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
        body = {
            **self._build_body(messages, model, temperature, max_tokens, system),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", _API_URL, headers=self._headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw in ("", "[DONE]"):
                        continue
                    import json

                    event = json.loads(raw)
                    delta = event.get("delta", {}).get("text") or event.get("delta", {}).get(
                        "content", ""
                    )
                    if delta:
                        yield delta

    async def embed(self, text: str, *, model: str = "") -> EmbedResponse:
        raise NotImplementedError(_EMBED_NOT_SUPPORTED)
