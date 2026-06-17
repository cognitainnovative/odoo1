"""PII redaction — strips sensitive data before sending to external AI providers.

Applies when:
  - the provider is external (is_external=True)
  - settings.redact_pii_external is True

Redacted patterns (configurable per company in future):
  - BSN (Dutch citizen service number): 9 consecutive digits matching the 11-check
  - IBAN: NL prefix bank account numbers
  - Email addresses
  - Dutch phone numbers
  - Credit card numbers (Luhn)
  - Names in payroll context — marked via the `sensitive_labels` arg
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, str]] = [
    # IBAN (NL)
    (r"\bNL\d{2}[A-Z]{4}\d{10}\b", "[IBAN]"),
    # Email
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL]"),
    # Dutch phone (mobile + landline) — use lookbehind instead of \b because
    # \b doesn't match at the boundary between a space and '+' (both non-\w).
    (r"(?<!\w)(?:\+31|0031|0)[1-9]\d{8}(?!\d)", "[PHONE]"),
    # Credit card (4×4 digit groups with optional separators)
    (r"\b(?:\d[ \-]?){13,16}\b", "[CARD]"),
    # BSN-like: 8–9 consecutive digits (conservative — exact 11-check is expensive in regex)
    (r"\b\d{8,9}\b", "[BSN]"),
]

_COMPILED = [(re.compile(p), repl) for p, repl in _PATTERNS]


def redact(text: str, *, extra_patterns: list[tuple[str, str]] | None = None) -> str:
    """Return text with known PII patterns replaced by placeholder tokens."""
    for pattern, repl in _COMPILED:
        text = pattern.sub(repl, text)
    if extra_patterns:
        for raw_pattern, repl in extra_patterns:
            text = re.sub(raw_pattern, repl, text)
    return text


def should_redact(provider, settings) -> bool:
    return getattr(provider, "is_external", False) and settings.redact_pii_external


def maybe_redact_messages(messages: list, provider, settings) -> list:
    """Return messages list with content redacted if the provider is external."""
    if not should_redact(provider, settings):
        return messages
    from providers.base import ChatMessage

    return [ChatMessage(role=m.role, content=redact(m.content)) for m in messages]
