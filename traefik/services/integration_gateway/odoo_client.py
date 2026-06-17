"""Thin Odoo JSON-RPC client — forwards normalised webhook payloads."""
from __future__ import annotations

import logging

import httpx

_logger = logging.getLogger(__name__)


class OdooClient:
    def __init__(self, base_url: str, db: str, username: str, password: str):
        self._base = base_url.rstrip("/")
        self._db = db
        self._username = username
        self._password = password
        self._uid: int | None = None

    async def _authenticate(self) -> int:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/web/dataset/call_kw",
                json={
                    "jsonrpc": "2.0", "method": "call", "id": 1,
                    "params": {
                        "model": "res.users",
                        "method": "authenticate",
                        "args": [self._db, self._username, self._password, {}],
                        "kwargs": {},
                    },
                },
            )
            resp.raise_for_status()
            uid = resp.json().get("result")
            if not uid:
                raise RuntimeError("Odoo authentication failed")
            return uid

    async def call(self, model: str, method: str, args: list, kwargs: dict | None = None) -> object:
        if self._uid is None:
            self._uid = await self._authenticate()
        payload = {
            "jsonrpc": "2.0", "method": "call", "id": 1,
            "params": {
                "model": model,
                "method": method,
                "args": args,
                "kwargs": kwargs or {},
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/web/dataset/call_kw",
                json=payload,
                cookies={"session_id": ""},
            )
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            _logger.error("Odoo RPC error: %s", data["error"])
            raise RuntimeError(data["error"].get("data", {}).get("message", "Odoo error"))
        return data.get("result")


_client: OdooClient | None = None


def get_odoo_client() -> OdooClient:
    global _client
    if _client is None:
        from config import get_settings
        s = get_settings()
        _client = OdooClient(s.odoo_url, s.odoo_db, s.odoo_admin_user, s.odoo_admin_password)
    return _client
