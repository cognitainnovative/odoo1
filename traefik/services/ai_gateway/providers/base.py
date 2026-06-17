"""Abstract provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # system | user | assistant
    content: str


class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"


class EmbedResponse(BaseModel):
    embedding: list[float]
    model: str
    provider: str
    token_count: int = 0


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system: str = "",
    ) -> ChatResponse: ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system: str = "",
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def embed(self, text: str, *, model: str = "") -> EmbedResponse: ...

    @property
    def is_external(self) -> bool:
        """True for providers that send data outside the network."""
        return False
