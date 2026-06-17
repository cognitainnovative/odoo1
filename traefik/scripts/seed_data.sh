#!/usr/bin/env bash
# Load demo / seed data via Odoo shell.
# Extend this script as modules are built.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ODOO_BIN="/home/diviner/Odoo/19/odoo-bin"
ODOO_CONF="$PROJECT_DIR/config/odoo.conf"
DB="platform_dev"

echo "Loading seed data into '$DB' …"

cd /home/diviner/Odoo/19
python3 "$ODOO_BIN" shell \
    -c "$ODOO_CONF" \
    -d "$DB" <<'PYSHELL'
# ── Seed: demo company + admin user ──────────────────────────────────────────
env = self.env

company = env['res.company'].search([('name', '=', 'Platform Demo')], limit=1)
if not company:
    company = env['res.company'].create({
        'name': 'Platform Demo',
        'email': 'admin@platformdemo.test',
        'country_id': env.ref('base.nl').id,
    })
    print(f"Created company: {company.name}")
else:
    print(f"Company exists: {company.name}")

env.cr.commit()
print("Seed data loaded.")
PYSHELL
