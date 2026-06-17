"""Mock provider — used in CI/tests when no API keys are present."""

from __future__ import annotations

from collections.abc import AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, EmbedResponse


class MockProvider(BaseProvider):
    name = "mock"

    async def chat(self, messages: list[ChatMessage], *, model: str = "", **kwargs) -> ChatResponse:
        last = messages[-1].content if messages else ""
        return ChatResponse(
            content=f"[mock] Echo: {last[:120]}",
            model=model or "mock-1",
            provider="mock",
        )

    async def chat_stream(
        self, messages: list[ChatMessage], *, model: str = "", **kwargs
    ) -> AsyncIterator[str]:
        last = messages[-1].content if messages else ""
        words = f"[mock] Echo: {last[:120]}".split()
        for word in words:
            yield word + " "

    async def embed(self, text: str, *, model: str = "") -> EmbedResponse:
        # Stable 768-dim zero vector for tests
        dim = 768
        return EmbedResponse(
            embedding=[0.0] * dim,
            model=model or "mock-embed",
            provider="mock",
            token_count=len(text.split()),
        )
