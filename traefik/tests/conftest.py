"""Shared pytest fixtures for the cross-service suite (tests/api + tests/e2e).

Design: these tests run against a LIVE stack (`docker compose up -d`). When a component
is not reachable, the relevant fixture calls `pytest.skip(...)` with a clear reason rather
than failing — so the suite is green on a machine without the stack up, and meaningful when
it is. Pure-unit checks that need no stack (e.g. signature helpers) live alongside and run
unconditionally.
"""

from __future__ import annotations

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))

from fixtures.config import get_config  # noqa: E402
from fixtures.odoo_rpc import OdooRPC, OdooRPCError  # noqa: E402

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="session")
def cfg():
    return get_config()


def _reachable(url: str, timeout: float) -> bool:
    try:
        requests.get(url, timeout=timeout)
        return True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def ai_gateway(cfg):
    """requests-ready base URL for the AI gateway; skips if /health is down."""
    health = f"{cfg.ai_gateway_url}/health"
    try:
        r = requests.get(health, timeout=cfg.health_timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"AI gateway not reachable at {cfg.ai_gateway_url} ({exc})")

    sess = requests.Session()
    if cfg.ai_gateway_secret:
        sess.headers["Authorization"] = f"Bearer {cfg.ai_gateway_secret}"
    sess.base_url = cfg.ai_gateway_url  # type: ignore[attr-defined]
    sess.timeout = cfg.http_timeout  # type: ignore[attr-defined]
    return sess


@pytest.fixture(scope="session")
def integration_gateway(cfg):
    """requests-ready base URL for the integration gateway; skips if /health is down."""
    try:
        r = requests.get(f"{cfg.integration_gateway_url}/health", timeout=cfg.health_timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"Integration gateway not reachable at {cfg.integration_gateway_url} ({exc})")
    sess = requests.Session()
    sess.base_url = cfg.integration_gateway_url  # type: ignore[attr-defined]
    sess.timeout = cfg.http_timeout  # type: ignore[attr-defined]
    return sess


@pytest.fixture(scope="session")
def odoo(cfg):
    """Authenticated Odoo JSON-RPC client; skips if Odoo is down or auth fails."""
    if not _reachable(f"{cfg.odoo_url}/web/health", cfg.health_timeout) and not _reachable(
        cfg.odoo_url, cfg.health_timeout
    ):
        pytest.skip(f"Odoo not reachable at {cfg.odoo_url}")
    client = OdooRPC(cfg.odoo_url, cfg.odoo_db, cfg.odoo_user, cfg.odoo_password, cfg.http_timeout)
    try:
        client.login()
    except (OdooRPCError, requests.RequestException) as exc:
        pytest.skip(f"Odoo login failed on db '{cfg.odoo_db}' ({exc})")
    return client


@pytest.fixture
def test_partner(odoo):
    """A throwaway customer used by e2e flows."""
    pid = odoo.create("res.partner", {"name": "E2E Customer", "email": "e2e@example.com"})
    return pid
