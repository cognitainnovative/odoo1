#!/usr/bin/env bash
# Run the platform test suite. Pass addon names as args to narrow scope.
# Usage: ./scripts/run_tests.sh [addon1 addon2 ...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ODOO_BIN="/home/diviner/Odoo/19/odoo-bin"
ODOO_CONF="$PROJECT_DIR/config/odoo.conf"
TEST_DB="platform_test"

# Build module list — default to all custom addons that have tests/
if [ "$#" -gt 0 ]; then
    MODULES="$*"
else
    MODULES=$(find "$PROJECT_DIR/addons" -mindepth 1 -maxdepth 1 -type d \
        -exec test -d "{}/tests" \; -printf "%f," | sed 's/,$//')
fi

echo "════════════════════════════════════════════"
echo " Platform Test Suite"
echo " Modules : ${MODULES:-none}"
echo " DB      : $TEST_DB"
echo "════════════════════════════════════════════"

# Bootstrap test: connectivity checks
python3 - <<'PYCHECK'
import sys

# PostgreSQL
try:
    import psycopg2
    conn = psycopg2.connect(dbname="postgres", user="diviner")
    conn.close()
    print("✔  PostgreSQL reachable")
except Exception as e:
    print(f"✘  PostgreSQL: {e}"); sys.exit(1)

# pgvector (best-effort)
try:
    conn = psycopg2.connect(dbname="postgres", user="diviner")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_available_extensions WHERE name='vector'")
    if cur.fetchone():
        print("✔  pgvector extension available")
    else:
        print("⚠  pgvector not available (optional — install postgresql-pgvector)")
    conn.close()
except Exception as e:
    print(f"⚠  pgvector check skipped: {e}")

# Redis (warning-only — not required for Odoo unit tests)
try:
    import redis
    r = redis.Redis(
        host=__import__('os').environ.get('REDIS_HOST', 'localhost'),
        port=int(__import__('os').environ.get('REDIS_PORT', '6379')),
        socket_connect_timeout=3,
    )
    r.ping()
    print("✔  Redis reachable")
except Exception as e:
    print(f"⚠  Redis unavailable (Celery/pubsub features won't work): {e}")

# MinIO (warning-only — not required for Odoo unit tests)
try:
    import urllib.request, urllib.error
    minio_url = __import__('os').environ.get('MINIO_HEALTH_URL', 'http://localhost:9000/minio/health/live')
    req = urllib.request.urlopen(minio_url, timeout=3)
    if req.status == 200:
        print("✔  MinIO reachable")
    else:
        print(f"⚠  MinIO health returned HTTP {req.status} (object storage unavailable)")
except Exception as e:
    print(f"⚠  MinIO unavailable (object storage features won't work): {e}")
PYCHECK

if [ -z "${MODULES:-}" ]; then
    echo "No custom addons with tests found yet. Bootstrap checks passed."
    exit 0
fi

# Drop and recreate test DB (terminate lingering connections first)
psql -U diviner -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$TEST_DB' AND pid <> pg_backend_pid();" \
    2>/dev/null || true
dropdb -U diviner --if-exists "$TEST_DB" 2>/dev/null || true
createdb -U diviner "$TEST_DB" 2>/dev/null || true

cd /home/diviner/Odoo/19
python3 "$ODOO_BIN" \
    -c "$ODOO_CONF" \
    -d "$TEST_DB" \
    --http-port=8071 \
    --test-enable \
    --stop-after-init \
    -i "$MODULES" \
    --log-level=test

echo "All tests passed."
