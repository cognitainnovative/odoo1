"""Gateway redaction tests — PII masked before external calls."""

from providers.base import ChatMessage
from providers.mock import MockProvider
from redaction import maybe_redact_messages, redact, should_redact


class TestRedactFunction:
    """redact() strips configured PII patterns."""

    def test_email_redacted(self):
        out = redact("Send to user@example.com please")
        assert "user@example.com" not in out
        assert "[EMAIL]" in out

    def test_iban_redacted(self):
        out = redact("Pay to NL91ABNA0417164300")
        assert "NL91ABNA0417164300" not in out
        assert "[IBAN]" in out

    def test_dutch_phone_redacted(self):
        out = redact("Call me at +31612345678")
        assert "+31612345678" not in out
        assert "[PHONE]" in out

    def test_no_pii_unchanged(self):
        plain = "The weather is nice today."
        assert redact(plain) == plain

    def test_multiple_patterns_in_one_text(self):
        text = "Email: admin@co.com, IBAN: NL91ABNA0417164300"
        out = redact(text)
        assert "[EMAIL]" in out
        assert "[IBAN]" in out
        assert "admin@co.com" not in out

    def test_extra_patterns_applied(self):
        out = redact("SECRET-TOKEN-ABCD", extra_patterns=[("SECRET-TOKEN-[A-Z]+", "[TOKEN]")])
        assert "[TOKEN]" in out
        assert "SECRET-TOKEN-ABCD" not in out


class TestShouldRedact:
    """should_redact() returns True only for external providers with redaction on."""

    def test_mock_provider_not_redacted(self, mock_settings):
        p = MockProvider()
        assert not should_redact(p, mock_settings)

    def test_external_provider_redacted_when_enabled(self, mock_settings):
        class FakeExternal:
            is_external = True

        mock_settings.redact_pii_external = True
        assert should_redact(FakeExternal(), mock_settings)

    def test_external_provider_not_redacted_when_disabled(self, mock_settings):
        class FakeExternal:
            is_external = True

        mock_settings.redact_pii_external = False
        assert not should_redact(FakeExternal(), mock_settings)


class TestMaybeRedactMessages:
    """maybe_redact_messages() strips PII when provider is external."""

    def test_mock_messages_unchanged(self, mock_settings):
        msgs = [ChatMessage(role="user", content="Email: x@y.com")]
        result = maybe_redact_messages(msgs, MockProvider(), mock_settings)
        assert result is msgs  # same object returned

    def test_external_messages_redacted(self, mock_settings):
        class FakeExternal:
            is_external = True

        mock_settings.redact_pii_external = True
        msgs = [ChatMessage(role="user", content="Email: x@y.com")]
        result = maybe_redact_messages(msgs, FakeExternal(), mock_settings)
        assert result is not msgs
        assert "x@y.com" not in result[0].content
        assert "[EMAIL]" in result[0].content
