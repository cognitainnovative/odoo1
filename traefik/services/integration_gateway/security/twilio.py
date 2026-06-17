"""Verify Twilio webhook signatures.

Twilio signs requests with HMAC-SHA1 of URL + sorted POST params.
Header: X-Twilio-Signature: <base64_digest>
"""
import base64
import hashlib
import hmac


def verify_twilio_signature(
    auth_token: str,
    url: str,
    post_params: dict,
    signature: str,
) -> bool:
    """Return True when the Twilio signature is valid.

    Passes silently when auth_token is empty (dev/sandbox mode).
    """
    if not auth_token:
        return True
    if not signature:
        return False
    # Build the signing string: URL + sorted key+value pairs
    signing = url + "".join(f"{k}{v}" for k, v in sorted(post_params.items()))
    mac = hmac.new(auth_token.encode(), signing.encode(), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)
