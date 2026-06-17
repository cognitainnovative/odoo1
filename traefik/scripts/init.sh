#!/usr/bin/env bash
# First-time project setup: create DB, enable pgvector, install base.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ODOO_BIN="/home/diviner/Odoo/19/odoo-bin"
ODOO_CONF="$PROJECT_DIR/config/odoo.conf"
DB="platform_dev"

echo "═══════════════════════════════════════════════"
echo " Platform Dev — First-time Init"
echo "═══════════════════════════════════════════════"

# Create DB
createdb -U diviner "$DB" 2>/dev/null && echo "✔  Database '$DB' created." \
    || echo "ℹ  Database '$DB' already exists."

# Enable pgvector (optional — won't fail if not installed)
psql -U diviner "$DB" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null \
    && echo "✔  pgvector enabled." \
    || echo "⚠  pgvector not installed (optional). Install with: sudo apt install postgresql-16-pgvector"

# Initialise Odoo
echo ""
echo "Installing Odoo base (this takes 1-2 minutes)…"
cd /home/diviner/Odoo/19
python3 "$ODOO_BIN" \
    -c "$ODOO_CONF" \
    -d "$DB" \
    -i base \
    --stop-after-init \
    --without-demo=False

echo ""
echo "═══════════════════════════════════════════════"
echo " Init complete. Run:  make up"
echo " Then open:           http://localhost:8070"
echo "═══════════════════════════════════════════════"
