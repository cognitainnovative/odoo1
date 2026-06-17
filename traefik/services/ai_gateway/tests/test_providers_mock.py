"""Gateway provider tests — mock provider returns deterministic results without network."""

import pytest
from providers.base import ChatMessage
from providers.factory import get_embed_provider, get_provider
from providers.mock import MockProvider


class TestMockProvider:
    """MockProvider: /complete and /embed return deterministic results, no network."""

    @pytest.mark.asyncio
    async def test_chat_returns_response(self):
        p = MockProvider()
        resp = await p.chat([ChatMessage(role="user", content="Hello")])
        assert resp.content.startswith("[mock]")
        assert resp.provider == "mock"

    @pytest.mark.asyncio
    async def test_chat_echoes_last_message(self):
        p = MockProvider()
        resp = await p.chat([ChatMessage(role="user", content="ping")])
        assert "ping" in resp.content

    @pytest.mark.asyncio
    async def test_embed_returns_768_dim_vector(self):
        p = MockProvider()
        resp = await p.embed("some text to embed")
        assert len(resp.embedding) == 768
        assert all(v == 0.0 for v in resp.embedding)
        assert resp.provider == "mock"

    @pytest.mark.asyncio
    async def test_embed_token_count_nonzero(self):
        p = MockProvider()
        resp = await p.embed("four words here")
        assert resp.token_count > 0

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tokens(self):
        p = MockProvider()
        tokens = []
        # chat_stream is an async generator (not a coroutine) — iterate directly
        async for tok in p.chat_stream([ChatMessage(role="user", content="hi")]):
            tokens.append(tok)
        assert len(tokens) > 0
        assert "".join(tokens).startswith("[mock]")

    @pytest.mark.asyncio
    async def test_deterministic_embed(self):
        """Same input always returns same embedding (for reproducible RAG tests)."""
        p = MockProvider()
        r1 = await p.embed("constant text")
        r2 = await p.embed("constant text")
        assert r1.embedding == r2.embedding


class TestProviderFactory:
    """Factory falls back to mock when no credentials are configured."""

    def test_factory_returns_mock_when_no_key(self, mock_settings):
        mock_settings.default_provider = "anthropic"
        mock_settings.anthropic_api_key = ""
        provider = get_provider("anthropic", settings=mock_settings)
        assert provider.name == "mock"

    def test_factory_returns_mock_explicitly(self, mock_settings):
        provider = get_provider("mock", settings=mock_settings)
        assert isinstance(provider, MockProvider)

    def test_embed_factory_returns_mock(self, mock_settings):
        mock_settings.embedding_provider = "mock"
        provider = get_embed_provider(settings=mock_settings)
        assert isinstance(provider, MockProvider)

    def test_factory_no_code_falls_back_to_default(self, mock_settings):
        mock_settings.default_provider = "mock"
        provider = get_provider(settings=mock_settings)
        assert isinstance(provider, MockProvider)
