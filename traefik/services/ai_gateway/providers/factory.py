"""Instantiate a provider from settings or an explicit code."""

from __future__ import annotations

from .base import BaseProvider
from .mock import MockProvider


def get_provider(code: str = "", settings=None) -> BaseProvider:
    """Return a configured provider instance.

    Falls back to MockProvider if the requested provider has no credentials.
    """
    if settings is None:
        from config import get_settings

        settings = get_settings()

    code = (code or settings.default_provider).lower()

    if code == "anthropic":
        if settings.anthropic_api_key:
            from .anthropic import AnthropicProvider

            return AnthropicProvider(
                api_key=settings.anthropic_api_key, model=settings.default_model
            )
    elif code == "openai":
        if settings.openai_api_key:
            from .openai import OpenAIProvider

            return OpenAIProvider(api_key=settings.openai_api_key, model=settings.default_model)
    elif code == "azure":
        if settings.azure_openai_api_key and settings.azure_openai_endpoint:
            from .openai import AzureOpenAIProvider

            return AzureOpenAIProvider(
                api_key=settings.azure_openai_api_key,
                endpoint=settings.azure_openai_endpoint,
                deployment=settings.azure_openai_deployment,
            )
    elif code == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(
            base_url=settings.ollama_base_url, model=settings.default_model or "llama3.2"
        )

    return MockProvider()


def get_embed_provider(settings=None) -> BaseProvider:
    if settings is None:
        from config import get_settings

        settings = get_settings()
    code = settings.embedding_provider.lower()
    if code == "openai" and settings.openai_api_key:
        from .openai import OpenAIProvider

        return OpenAIProvider(api_key=settings.openai_api_key)
    if code == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.embedding_model)
    return MockProvider()
