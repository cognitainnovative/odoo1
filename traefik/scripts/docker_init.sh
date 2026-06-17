#!/usr/bin/env bash
# scripts/docker_init.sh — first-run initialisation for the DOCKER stack.
#
# Odoo does not auto-initialise an empty database, so a fresh `docker compose up`
# serves HTTP 500 until the addons are installed once. This script does that
# install. It is SAFE TO RE-RUN: if the database is already initialised it exits
# without doing anything.
#
# (For the native dev setup use `scripts/init.sh` / `make init` instead.)
#
# Usage:
#   ./scripts/docker_init.sh
#   COMPOSE_PROJECT=verify ./scripts/docker_init.sh   # isolated project name
set -euo pipefail

cd "$(dirname "$0")/.."

DB="${POSTGRES_DB:-platform_dev}"
PGUSER="${POSTGRES_USER:-odoo}"

COMPOSE=(docker compose)
[ -n "${COMPOSE_PROJECT:-}" ] && COMPOSE=(docker compose -p "$COMPOSE_PROJECT")

echo "==> Ensuring .env exists"
[ -f .env ] || cp .env.example .env

echo "==> Starting stack"
"${COMPOSE[@]}" up -d

echo "==> Waiting for Postgres ($DB) to accept connections"
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T db pg_isready -U "$PGUSER" -d "$DB" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Checking whether '$DB' is already initialised"
ALREADY=$("${COMPOSE[@]}" exec -T db psql -U "$PGUSER" -d "$DB" -tAc \
  "SELECT to_regclass('public.ir_module_module') IS NOT NULL;" 2>/dev/null | tr -d '[:space:]' || echo "f")

if [ "$ALREADY" = "t" ]; then
  echo "==> '$DB' already initialised — nothing to do."
  exit 0
fi

echo "==> First run: installing all custom addons (~2 min)"
MODULES=$("${COMPOSE[@]}" exec -T odoo sh -c \
  "ls -d /mnt/extra-addons/custom_* | xargs -n1 basename | paste -sd,")
echo "    Modules: $MODULES"

# --no-http avoids binding 8069 while the main Odoo process already holds it.
"${COMPOSE[@]}" exec -T odoo odoo -d "$DB" -i "$MODULES" --stop-after-init --no-http

echo "==> Restarting Odoo"
"${COMPOSE[@]}" restart odoo

echo ""
echo "==> Done. Verify with:"
echo "    curl -s localhost:8069/web/health    # -> {\"status\": \"pass\"}"
