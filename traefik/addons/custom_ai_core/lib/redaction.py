"""PII redaction utilities for AI input data-minimization."""

import re

# Default redaction patterns — ordered (most specific first).
# IMPORTANT: the credit-card pattern MUST precede the generic phone pattern,
# otherwise a 16-digit card is greedily caught and mislabeled [PHONE-REDACTED].
_DEFAULT_PATTERNS = [
    # Credit/debit card numbers (16 digits, optionally grouped) — most specific
    (re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"), "[CARD-REDACTED]"),
    # IBAN (NL format and generic)
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"), "[IBAN-REDACTED]"),
    # Dutch BSN (burgerservicenummer) — 9 digits
    (re.compile(r"\b\d{9}\b"), "[BSN-REDACTED]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL-REDACTED]"),
    # Dutch phone numbers
    (re.compile(r"\b(\+31|0031|0)\s?[1-9]\d{8}\b"), "[PHONE-REDACTED]"),
    # Generic phone numbers (broad — kept last so specific patterns win)
    (re.compile(r"\+?\d[\d\s\-\(\)]{7,}\d"), "[PHONE-REDACTED]"),
]


def redact(text: str, extra_patterns: list | None = None) -> tuple[str, bool]:
    """Redact PII from *text* before sending to an external AI provider.

    Returns (redacted_text, was_changed).
    """
    if not text:
        return text, False

    result = text
    for pattern, replacement in _DEFAULT_PATTERNS:
        result = pattern.sub(replacement, result)

    if extra_patterns:
        for raw_pattern, replacement in extra_patterns:
            try:
                result = re.sub(raw_pattern, replacement, result)
            except re.error:
                pass  # bad pattern — skip

    return result, result != text
