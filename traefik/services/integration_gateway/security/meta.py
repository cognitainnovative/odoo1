"""Verify Meta / WhatsApp Cloud API webhook signatures.

Meta signs requests with HMAC-SHA256 of the raw body using the App Secret.
Header: X-Hub-Signature-256: sha256=<hex_digest>
"""
import hashlib
import hmac


def verify_meta_signature(body: bytes, signature_header: str, app_secret: str) -> bool:
    """Return True if the signature matches; False otherwise.

    Passes silently when app_secret is empty (dev/sandbox mode).
    """
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header[7:]
    return hmac.compare_digest(expected, provided)
