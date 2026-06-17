#!/usr/bin/env bash
# Restore latest (or specified) backup to platform_dev.
# Usage: ./scripts/restore.sh [backup_file.dump]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB="platform_dev"
BACKUP_DIR="$PROJECT_DIR/backups"

if [ -n "${1:-}" ]; then
    DUMP_FILE="$1"
else
    DUMP_FILE="$(ls -t "$BACKUP_DIR"/*.dump 2>/dev/null | head -1)"
    if [ -z "$DUMP_FILE" ]; then
        echo "No backup dumps found in $BACKUP_DIR"; exit 1
    fi
fi

echo "Restoring '$DUMP_FILE' → database '$DB' …"
echo "WARNING: This will DROP and recreate the '$DB' database!"
read -r -p "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

dropdb -U diviner --if-exists "$DB"
createdb -U diviner "$DB"
pg_restore -U diviner -d "$DB" --no-owner --role=diviner "$DUMP_FILE"

# Restore filestore if present
FILESTORE_ARCHIVE="${DUMP_FILE%.dump}.filestore.tar.gz"
if [ -f "$FILESTORE_ARCHIVE" ]; then
    DEST_DIR="$PROJECT_DIR/.odoo_data/filestore"
    mkdir -p "$DEST_DIR"
    tar -xzf "$FILESTORE_ARCHIVE" -C "$DEST_DIR"
    echo "Filestore restored."
fi

echo "Restore complete."
