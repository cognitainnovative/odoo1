#!/usr/bin/env bash
# Start Odoo dev server in the foreground (use 'make up' for background)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ODOO_BIN="/home/diviner/Odoo/19/odoo-bin"
ODOO_CONF="$PROJECT_DIR/config/odoo.conf"

mkdir -p "$PROJECT_DIR/logs"

echo "Starting Odoo on http://localhost:8070 (foreground) …"
echo "Press Ctrl+C to stop."
echo ""

cd /home/diviner/Odoo/19
exec python3 "$ODOO_BIN" -c "$ODOO_CONF" "$@"
