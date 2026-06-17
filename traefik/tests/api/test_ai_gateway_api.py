"""API tests for the AI gateway.

Deterministic where possible (mock chat provider, standalone redaction). Endpoints that
require a live embedding provider (Ollama, or EMBEDDING_PROVIDER=mock) are asserted
tolerantly: a 502 means "no embedding backend wired in this environment", which is a
deployment fact, not a code defect.
"""

import uuid

import requests


def test_health(ai_gateway):
    r = ai_gateway.get(f"{ai_gateway.base_url}/health", timeout=ai_gateway.timeout)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_chat_mock_provider_echoes(ai_gateway):
    payload = {
        "messages": [{"role": "user", "content": "Hello platform"}],
        "provider": "mock",
    }
    r = ai_gateway.post(f"{ai_gateway.base_url}/chat", json=payload, timeout=ai_gateway.timeout)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "mock"
    assert "[mock]" in body["content"]
    assert "Hello platform"[:20] in body["content"]


def test_redaction_masks_pii(ai_gateway):
    # Email + NL IBAN are masked by the gateway's redaction patterns.
    text = "Contact john.doe@example.com, account NL11RABO0987654321."
    r = ai_gateway.post(
        f"{ai_gateway.base_url}/rag/redact", json={"text": text}, timeout=ai_gateway.timeout
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["was_changed"] is True
    assert "john.doe@example.com" not in body["redacted_text"]
    assert "NL11RABO0987654321" not in body["redacted_text"]
    assert "[EMAIL]" in body["redacted_text"]


def test_rag_query_shape(ai_gateway):
    payload = {"question": "What is the refund policy?", "company_id": 1, "provider": "mock"}
    r = ai_gateway.post(
        f"{ai_gateway.base_url}/rag/query", json=payload, timeout=ai_gateway.timeout
    )
    assert r.status_code in (200, 502), r.text
    if r.status_code == 200:
        body = r.json()
        assert "answer" in body
        assert isinstance(body["sources"], list)  # cited chunks (possibly empty corpus)
        assert "provider" in body


def test_embed_shape(ai_gateway):
    r = ai_gateway.post(
        f"{ai_gateway.base_url}/embed", json={"text": "embed me"}, timeout=ai_gateway.timeout
    )
    assert r.status_code in (200, 502), r.text
    if r.status_code == 200:
        body = r.json()
        assert isinstance(body["embedding"], list) and body["embedding"]
        assert "provider" in body


def test_rag_ingest_query_delete_roundtrip(ai_gateway):
    """Full RAG lifecycle; skips gracefully if no embedding backend is wired."""
    import pytest

    company = 4242
    doc_id = f"e2e-{uuid.uuid4().hex[:8]}"
    files = {
        "file": ("policy.txt", b"Refunds are issued within 14 days of purchase.", "text/plain")
    }
    data = {"doc_id": doc_id, "company_id": str(company)}
    r = ai_gateway.post(
        f"{ai_gateway.base_url}/rag/ingest", files=files, data=data, timeout=ai_gateway.timeout
    )
    if r.status_code == 502:
        pytest.skip("No embedding backend available (set EMBEDDING_PROVIDER=mock or run Ollama)")
    assert r.status_code == 200, r.text
    assert r.json()["doc_id"] == doc_id

    # Tenant isolation: a different company must not retrieve this doc.
    q_other = ai_gateway.post(
        f"{ai_gateway.base_url}/rag/query",
        json={"question": "refund window", "company_id": company + 1, "provider": "mock"},
        timeout=ai_gateway.timeout,
    )
    if q_other.status_code == 200:
        other_docs = {s["doc_id"] for s in q_other.json()["sources"]}
        assert doc_id not in other_docs

    # Cleanup deletes embeddings too.
    d = ai_gateway.delete(
        f"{ai_gateway.base_url}/rag/document/{doc_id}",
        params={"company_id": company},
        timeout=ai_gateway.timeout,
    )
    assert d.status_code == 200, d.text


def test_auth_enforced_when_secret_set(cfg, ai_gateway):
    """If a Bearer secret is configured, an unauthenticated call must be rejected."""
    import pytest

    if not cfg.ai_gateway_secret:
        pytest.skip("AI_GATEWAY_SECRET not set — auth is intentionally open in dev")
    r = requests.post(
        f"{cfg.ai_gateway_url}/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "provider": "mock"},
        timeout=cfg.http_timeout,
    )
    assert r.status_code == 401
