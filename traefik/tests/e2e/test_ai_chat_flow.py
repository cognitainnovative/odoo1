"""E2E: AI website chat (Section 8 critical flow).

visitor starts a session → sends a message → receives an AI reply with citations and an
escalation flag. Exercises the public chat controllers end to end (Odoo → ai_core →
ai_gateway). Runs against the mock provider by default.
"""

import requests


def _jsonrpc(url: str, path: str, params: dict, timeout: float):
    payload = {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
    return requests.post(f"{url}{path}", json=payload, timeout=timeout)


def test_visitor_chat_returns_reply(odoo, cfg):
    start = _jsonrpc(cfg.odoo_url, "/chatbot/start", {"language": "en"}, cfg.http_timeout)
    assert start.status_code == 200, start.text
    session = start.json()["result"]
    session_id = session["session_id"]
    assert session_id

    msg = _jsonrpc(
        cfg.odoo_url,
        "/chatbot/message",
        {"session_id": session_id, "message": "What are your opening hours?"},
        cfg.http_timeout,
    )
    assert msg.status_code == 200, msg.text
    result = msg.json()["result"]
    assert "reply" in result and isinstance(result["reply"], str) and result["reply"]
    assert "escalated" in result
    assert "citations" in result  # cited sources (possibly empty if KB is empty)
