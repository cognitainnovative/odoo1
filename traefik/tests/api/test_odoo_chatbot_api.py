"""API tests for the public chatbot controllers (Odoo `type=jsonrpc`, `auth=public`).

These exercise the website chat entry points without a logged-in session, the way the
embedded widget calls them.
"""

import requests


def _jsonrpc(url: str, path: str, params: dict, timeout: float):
    payload = {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
    r = requests.post(f"{url}{path}", json=payload, timeout=timeout)
    return r


def test_chatbot_config(odoo, cfg):
    """`/chatbot/config` returns a config dict; `enabled` reflects whether chat is set up."""
    r = _jsonrpc(cfg.odoo_url, "/chatbot/config", {}, cfg.http_timeout)
    assert r.status_code == 200, r.text
    result = r.json().get("result")
    assert isinstance(result, dict)
    assert "enabled" in result


def test_chatbot_start_session(odoo, cfg):
    """`/chatbot/start` returns a visitor token + session id (creating them if needed)."""
    r = _jsonrpc(cfg.odoo_url, "/chatbot/start", {"language": "en"}, cfg.http_timeout)
    assert r.status_code == 200, r.text
    result = r.json().get("result")
    assert isinstance(result, dict)
    assert result.get("visitor_token")
    assert result.get("session_id")
