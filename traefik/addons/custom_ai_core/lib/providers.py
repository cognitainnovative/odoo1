"""AI provider implementations.

Each provider wraps one external (or local) LLM API.
All providers share the same interface: call(messages, **kwargs) → AiResponse.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class AiMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class AiResponse:
    content: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class BaseProvider:
    code: str = "base"
    name: str = "Base"

    def call(
        self,
        messages: list[AiMessage],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AiResponse:
        raise NotImplementedError

    def embed(self, text: str, model: str = "") -> list[float]:
        """Return an embedding vector for *text*. Empty list if unsupported."""
        return []


class MockProvider(BaseProvider):
    """Returns deterministic responses for tests and CI — no network required."""

    code = "mock"
    name = "Mock (Testing)"

    _DEFAULT_REPLY = (
        "This is a mock AI response. "
        "Configure a real provider (Anthropic, OpenAI, or Ollama) to enable live AI features."
    )

    def call(self, messages, model="", temperature=0.7, max_tokens=2048, **kwargs):
        t0 = time.monotonic()
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        # Echo the last user message as a prefix so tests can assert on it
        reply = f"[MOCK] {self._DEFAULT_REPLY} | Echo: {last_user[:80]}"
        return AiResponse(
            content=reply,
            model="mock-v1",
            input_tokens=sum(len(m.content.split()) for m in messages),
            output_tokens=len(reply.split()),
            latency_ms=int((time.monotonic() - t0) * 1000),
            provider=self.code,
        )

    def embed(self, text, model=""):
        # Return a 128-dim zero vector so embedding tests can run without real models
        return [0.0] * 128


class AnthropicProvider(BaseProvider):
    code = "anthropic"
    name = "Anthropic (Claude)"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self._api_key = api_key
        self._default_model = model

    def call(self, messages, model="", temperature=0.7, max_tokens=2048, **kwargs):
        import requests

        model = model or self._default_model
        t0 = time.monotonic()

        system_parts = [m.content for m in messages if m.role == "system"]
        chat_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            return AiResponse(
                content=content,
                model=model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                latency_ms=int((time.monotonic() - t0) * 1000),
                provider=self.code,
            )
        except Exception as exc:
            _logger.warning("Anthropic API call failed: %s", exc)
            return AiResponse(content="", model=model, provider=self.code, error=str(exc))


class OpenAiProvider(BaseProvider):
    """Handles OpenAI, Azure OpenAI, and any OpenAI-compatible endpoint (e.g. Ollama)."""

    code = "openai"
    name = "OpenAI / Azure"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ):
        self._api_key = api_key
        self._default_model = model
        self._base_url = base_url.rstrip("/")

    def call(self, messages, model="", temperature=0.7, max_tokens=2048, **kwargs):
        import requests

        model = model or self._default_model
        t0 = time.monotonic()

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return AiResponse(
                content=content,
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=int((time.monotonic() - t0) * 1000),
                provider=self.code,
            )
        except Exception as exc:
            _logger.warning("OpenAI API call failed: %s", exc)
            return AiResponse(content="", model=model, provider=self.code, error=str(exc))

    def embed(self, text, model="text-embedding-3-small"):
        import requests

        try:
            resp = requests.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": text, "model": model},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception as exc:
            _logger.warning("OpenAI embedding failed: %s", exc)
            return []


class OllamaProvider(BaseProvider):
    """Local Ollama server — zero data egress, mandatory for payroll/financial content."""

    code = "ollama"
    name = "Ollama (Local)"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self._base_url = base_url.rstrip("/")
        self._default_model = model

    def call(self, messages, model="", temperature=0.7, max_tokens=2048, **kwargs):
        import requests

        model = model or self._default_model
        t0 = time.monotonic()

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["message"]["content"]
            return AiResponse(
                content=content,
                model=model,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                latency_ms=int((time.monotonic() - t0) * 1000),
                provider=self.code,
            )
        except Exception as exc:
            _logger.warning("Ollama call failed: %s", exc)
            return AiResponse(content="", model=model, provider=self.code, error=str(exc))

    def embed(self, text, model="nomic-embed-text"):
        import requests

        try:
            resp = requests.post(
                f"{self._base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as exc:
            _logger.warning("Ollama embedding failed: %s", exc)
            return []


class AzureOpenAiProvider(BaseProvider):
    """Azure OpenAI Service — uses api-key auth + api-version query param."""

    code = "azure"
    name = "Azure OpenAI"

    def __init__(self, api_key: str, base_url: str = "", model: str = "gpt-4o"):
        self._api_key = api_key
        self._default_model = model
        # base_url must be the full deployment endpoint, e.g.:
        # https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completions
        self._base_url = base_url.rstrip("/") if base_url else ""

    def call(self, messages, model="", temperature=0.7, max_tokens=2048, **kwargs):
        import requests

        if not self._base_url:
            return AiResponse(
                content="",
                model=self._default_model,
                provider=self.code,
                error="Azure endpoint not configured. Set base_url to your deployment URL.",
            )
        t0 = time.monotonic()
        payload: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = requests.post(
                f"{self._base_url}?api-version=2024-02-15-preview",
                headers={"api-key": self._api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return AiResponse(
                content=content,
                model=model or self._default_model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=int((time.monotonic() - t0) * 1000),
                provider=self.code,
            )
        except Exception as exc:
            _logger.warning("Azure OpenAI call failed: %s", exc)
            return AiResponse(
                content="", model=model or self._default_model, provider=self.code, error=str(exc)
            )


def get_provider(code: str, api_key: str = "", base_url: str = "", model: str = "") -> BaseProvider:
    """Factory: return the correct provider instance for the given code."""
    if code == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or "claude-haiku-4-5-20251001")
    if code == "openai":
        return OpenAiProvider(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            base_url=base_url or "https://api.openai.com/v1",
        )
    if code == "azure":
        return AzureOpenAiProvider(api_key=api_key, base_url=base_url, model=model or "gpt-4o")
    if code == "ollama":
        return OllamaProvider(
            base_url=base_url or "http://localhost:11434",
            model=model or "llama3.2",
        )
    # Default: mock
    return MockProvider()
