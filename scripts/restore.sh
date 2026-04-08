#!/bin/bash
# DecisionDoc AI — Data Restore Script
# Usage: ./scripts/restore.sh <backup_file> [target_data_dir]
# Example: ./scripts/restore.sh /backup/decisiondoc/data-20250317-020000.tar.gz

set -euo pipefail

BACKUP_FILE=${1:-""}
TARGET_DIR=${2:-./data}

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup_file> [target_data_dir]"
  echo ""
  echo "Available backups:"
  ls -lht /backup/decisiondoc/data-*.tar.gz 2>/dev/null || echo "  (none found in /backup/decisiondoc/)"
  exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "⚠️  WARNING: This will replace ALL data in $TARGET_DIR"
echo "   Backup: $BACKUP_FILE"
echo ""
read -rp "Type 'yes' to confirm: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Aborted."
  exit 0
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Stop app if running
echo "[$(date -Iseconds)] Stopping application..."
docker compose stop app 2>/dev/null || true

# Backup current data before restoring
if [[ -d "$TARGET_DIR" ]]; then
  SAFETY_BACKUP="$(dirname "$TARGET_DIR")/data-pre-restore-${TIMESTAMP}.tar.gz"
  echo "[$(date -Iseconds)] Saving current data to $SAFETY_BACKUP..."
  tar czf "$SAFETY_BACKUP" -C "$(dirname "$TARGET_DIR")" "$(basename "$TARGET_DIR")" || true
fi

# Restore
echo "[$(date -Iseconds)] Restoring from $BACKUP_FILE..."
mkdir -p "$(dirname "$TARGET_DIR")"
rm -rf "$TARGET_DIR"
tar xzf "$BACKUP_FILE" -C "$(dirname "$TARGET_DIR")"

echo "[$(date -Iseconds)] Restore complete. Data directory: $TARGET_DIR"

# Restart app
echo "[$(date -Iseconds)] Restarting application..."
docker compose start app 2>/dev/null || true

echo "[$(date -Iseconds)] ✅ Restore finished successfully."
