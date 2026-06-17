"""Tiny Odoo JSON-RPC client used by the e2e and API tests.

Uses the stable external API (`/jsonrpc`, services `common` + `object`), so it does
not depend on a web session or CSRF token. Only the standard library + `requests`.
"""

from __future__ import annotations

import itertools
from typing import Any

import requests


class OdooRPCError(RuntimeError):
    """Raised when Odoo returns a JSON-RPC fault."""


class MethodMissingError(OdooRPCError):
    """Raised specifically when a model method does not exist.

    Distinguished from business-rule errors (ValidationError / UserError) so e2e
    tests can fail hard on a missing workflow method while tolerating guarded steps.
    """


_MISSING_MARKERS = (
    "has no attribute",
    "object has no method",
    "is not a valid action",
    "type object",
)


class OdooRPC:
    def __init__(self, url: str, db: str, username: str, password: str, timeout: float = 15.0):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.timeout = timeout
        self._ids = itertools.count(1)
        self.uid: int | None = None

    # ── low-level ────────────────────────────────────────────────────────────
    def _call(self, service: str, method: str, args: list) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": next(self._ids),
        }
        resp = requests.post(f"{self.url}/jsonrpc", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            err = data["error"]
            msg = (err.get("data", {}) or {}).get("message") or err.get("message") or str(err)
            debug = (err.get("data", {}) or {}).get("debug", "") or ""
            haystack = f"{msg}\n{debug}".lower()
            if any(m in haystack for m in _MISSING_MARKERS):
                raise MethodMissingError(msg)
            raise OdooRPCError(msg)
        return data.get("result")

    # ── session ──────────────────────────────────────────────────────────────
    def login(self) -> int:
        self.uid = self._call("common", "authenticate", [self.db, self.username, self.password, {}])
        if not self.uid:
            raise OdooRPCError("Authentication failed (check ODOO_DB / ODOO_USER / ODOO_PASSWORD)")
        return self.uid

    def version(self) -> dict:
        return self._call("common", "version", [])

    # ── ORM ──────────────────────────────────────────────────────────────────
    def execute(self, model: str, method: str, *args, **kw) -> Any:
        if self.uid is None:
            self.login()
        return self._call(
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, method, list(args), kw],
        )

    def create(self, model: str, values: dict) -> int:
        return self.execute(model, "create", values)

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        return self.execute(model, "write", ids, values)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.execute(model, "read", ids, fields)

    def search(self, model: str, domain: list, limit: int = 0) -> list[int]:
        kw = {"limit": limit} if limit else {}
        return self.execute(model, "search", domain, **kw)

    def search_read(
        self, model: str, domain: list, fields: list[str], limit: int = 0
    ) -> list[dict]:
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        return self.execute(model, "search_read", domain, **kw)

    def fields_get(self, model: str, attributes: list[str] | None = None) -> dict:
        return self.execute(
            model, "fields_get", [], attributes=attributes or ["required", "type", "relation"]
        )

    def model_exists(self, model: str) -> bool:
        return bool(self.search("ir.model", [["model", "=", model]], limit=1))

    # ── helpers ────────────────────────────────────────────────────────────────
    def call_action(self, model: str, ids: list[int], method: str) -> tuple[str, Any]:
        """Call a workflow action.

        Returns ("ok", result) on success, ("guarded", message) when a business rule
        (ValidationError / UserError) blocks the step. Raises MethodMissingError if the
        method does not exist on the model — that is a real defect, not a guarded step.
        """
        try:
            return "ok", self.execute(model, method, ids)
        except MethodMissingError:
            raise
        except OdooRPCError as exc:
            return "guarded", str(exc)

    def any_product(self) -> int | None:
        """Return the id of a sellable product, creating a simple one if none exists."""
        ids = self.search("product.product", [["sale_ok", "=", True]], limit=1)
        if ids:
            return ids[0]
        try:
            return self.create("product.product", {"name": "E2E Test Product", "list_price": 100.0})
        except OdooRPCError:
            return None
