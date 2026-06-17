"""Integration-gateway tests.

Two layers:
  1. Signature verification unit tests — import the real helpers from the service and run
     unconditionally (no live stack needed). These guard value-add #15: "webhook signature
     verification for all inbound providers".
  2. Live smoke tests against a running gateway (skipped if it is down).
"""

import base64
import hashlib
import hmac
import os
import sys

# Make the integration_gateway package importable for the unit-level signature tests.
_SVC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "services", "integration_gateway")
)
if _SVC not in sys.path:
    sys.path.insert(0, _SVC)

from security.meta import verify_meta_signature  # noqa: E402
from security.twilio import verify_twilio_signature  # noqa: E402


# ── 1. Signature verification (deterministic, no stack) ───────────────────────
class TestMetaSignature:
    def test_valid_signature_accepted(self):
        secret = "app-secret"
        body = b'{"object":"whatsapp_business_account"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_meta_signature(body, sig, secret) is True

    def test_tampered_body_rejected(self):
        secret = "app-secret"
        body = b'{"object":"whatsapp_business_account"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_meta_signature(b'{"object":"tampered"}', sig, secret) is False

    def test_missing_or_malformed_header_rejected(self):
        assert verify_meta_signature(b"x", "", "secret") is False
        assert verify_meta_signature(b"x", "md5=deadbeef", "secret") is False

    def test_empty_secret_passes_in_dev(self):
        assert verify_meta_signature(b"anything", "", "") is True


class TestTwilioSignature:
    def test_valid_signature_accepted(self):
        token = "twilio-token"
        url = "https://hooks.example.com/webhooks/voice/incoming/1"
        params = {"From": "+31600000000", "CallSid": "CA123"}
        signing = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
        sig = base64.b64encode(
            hmac.new(token.encode(), signing.encode(), hashlib.sha1).digest()
        ).decode()
        assert verify_twilio_signature(token, url, params, sig) is True

    def test_wrong_signature_rejected(self):
        assert verify_twilio_signature("token", "https://x/y", {"a": "b"}, "wrong") is False

    def test_empty_token_passes_in_dev(self):
        assert verify_twilio_signature("", "https://x/y", {"a": "b"}, "") is True


# ── 2. Live smoke tests (require a running gateway) ───────────────────────────
def test_health(integration_gateway):
    r = integration_gateway.get(
        f"{integration_gateway.base_url}/health", timeout=integration_gateway.timeout
    )
    assert r.status_code == 200


def test_whatsapp_verify_challenge(integration_gateway):
    """Meta subscription handshake echoes hub.challenge (200) or refuses (403)."""
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-token",
        "hub.challenge": "challenge-12345",
    }
    r = integration_gateway.get(
        f"{integration_gateway.base_url}/webhooks/whatsapp/1",
        params=params,
        timeout=integration_gateway.timeout,
    )
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert r.text == "challenge-12345"


def test_whatsapp_inbound_rejects_bad_input(integration_gateway):
    """A POST with a bogus signature / invalid JSON is rejected with a 4xx, never a 5xx."""
    r = integration_gateway.post(
        f"{integration_gateway.base_url}/webhooks/whatsapp/1",
        data=b"not-json",
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        timeout=integration_gateway.timeout,
    )
    assert r.status_code in (400, 401)
