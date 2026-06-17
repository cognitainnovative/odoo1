#!/usr/bin/env bash
# Dump platform_dev database + filestore to backups/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB="platform_dev"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$BACKUP_DIR/${DB}_${TIMESTAMP}"

mkdir -p "$BACKUP_DIR"

echo "Backing up database '$DB' → $DEST.dump …"
pg_dump -U diviner -Fc "$DB" > "${DEST}.dump"

echo "Backing up filestore → $DEST.filestore.tar.gz …"
FILESTORE="$PROJECT_DIR/.odoo_data/filestore/$DB"
if [ -d "$FILESTORE" ]; then
    tar -czf "${DEST}.filestore.tar.gz" -C "$(dirname "$FILESTORE")" "$DB"
else
    echo "  (No filestore found at $FILESTORE — skipped)"
fi

echo "Backup complete: $DEST"
