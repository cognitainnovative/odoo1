"""Test configuration resolved from environment variables.

Defaults match the docker-compose host port map so the suite "just works" after
`docker compose up -d`. Override any value via the environment in CI or against
a remote stack.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Odoo (JSON-RPC). Dev override exposes 8069 on the host; behind Traefik use
    # http://platform.localhost.
    odoo_url: str = os.environ.get("ODOO_URL", "http://localhost:8069")
    odoo_db: str = os.environ.get("ODOO_DB", "platform_dev")
    odoo_user: str = os.environ.get("ODOO_USER", "admin")
    odoo_password: str = os.environ.get("ODOO_PASSWORD", "admin")

    # FastAPI gateways (dev override exposes 8000 / 8001 on the host).
    ai_gateway_url: str = os.environ.get("AI_GATEWAY_URL", "http://localhost:8000")
    ai_gateway_secret: str = os.environ.get("AI_GATEWAY_SECRET", "")
    integration_gateway_url: str = os.environ.get(
        "INTEGRATION_GATEWAY_URL", "http://localhost:8001"
    )

    # Network timeouts (seconds).
    http_timeout: float = float(os.environ.get("TEST_HTTP_TIMEOUT", "15"))
    health_timeout: float = float(os.environ.get("TEST_HEALTH_TIMEOUT", "3"))


def get_config() -> Config:
    return Config()
