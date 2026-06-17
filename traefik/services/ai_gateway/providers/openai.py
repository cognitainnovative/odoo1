"""OpenAI + Azure OpenAI provider (Chat Completions + Embeddings API)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import BaseProvider, ChatMessage, ChatResponse, EmbedResponse

_OAI_CHAT = "https://api.openai.com/v1/chat/completions"
_OAI_EMBED = "https://api.openai.com/v1/embeddings"
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_EMBED = "text-embedding-3-small"


class OpenAIProvider(BaseProvider):
    name = "openai"
    is_external = True

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        base_url: str = "",
    ):
        self._api_key = api_key
        self._model = model
        self._chat_url = f"{base_url.rstrip('/')}/chat/completions" if base_url else _OAI_CHAT
        self._embed_url = f"{base_url.rstrip('/')}/embeddings" if base_url else _OAI_EMBED
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _messages_body(self, messages: list[ChatMessage], system: str) -> list[dict]:
        out = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend({"role": m.role, "content": m.content} for m in messages)
        return out

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
        body = {
            "model": model or self._model,
            "messages": self._messages_body(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self._chat_url, headers=self._headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResponse(
            content=choice["message"]["content"],
            model=data.get("model", model),
            provider="openai",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
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

        body = {
            "model": model or self._model,
            "messages": self._messages_body(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST", self._chat_url, headers=self._headers, json=body
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw in ("", "[DONE]"):
                        continue
                    event = json.loads(raw)
                    delta = event["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def embed(self, text: str, *, model: str = "") -> EmbedResponse:
        body = {"model": model or _DEFAULT_EMBED, "input": text}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._embed_url, headers=self._headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        embedding = data["data"][0]["embedding"]
        usage = data.get("usage", {})
        return EmbedResponse(
            embedding=embedding,
            model=data.get("model", model),
            provider="openai",
            token_count=usage.get("total_tokens", 0),
        )


class AzureOpenAIProvider(OpenAIProvider):
    """Azure OpenAI — same API surface, different base URL + auth header."""

    name = "azure"

    def __init__(
        self, api_key: str, endpoint: str, deployment: str, api_version: str = "2024-02-15-preview"
    ):
        base = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        super().__init__(api_key=api_key, model=deployment, base_url=base)
        # Azure uses a different auth header
        self._headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        self._chat_url = f"{base}/chat/completions?api-version={api_version}"
        self._embed_url = f"{base}/embeddings?api-version={api_version}"
