#!/bin/bash
# DecisionDoc AI — Data Backup Script
# Usage: ./scripts/backup.sh [backup_dir]
# Cron: 0 2 * * * /opt/decisiondoc/scripts/backup.sh >> /var/log/decisiondoc-backup.log 2>&1

set -euo pipefail

BACKUP_DIR=${1:-/backup/decisiondoc}
DATA_DIR=${DATA_DIR:-./data}
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/data-${TIMESTAMP}.tar.gz"
KEEP_DAYS=${BACKUP_KEEP_DAYS:-30}

echo "[$(date -Iseconds)] Starting backup..."

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Check data directory exists
if [[ ! -d "$DATA_DIR" ]]; then
  echo "[$(date -Iseconds)] ERROR: Data directory not found: $DATA_DIR"
  exit 1
fi

# Create compressed backup
tar czf "$BACKUP_FILE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)

echo "[$(date -Iseconds)] Backup created: $BACKUP_FILE ($SIZE)"

# Remove old backups
DELETED=$(find "$BACKUP_DIR" -name "data-*.tar.gz" -mtime "+${KEEP_DAYS}" -print -delete | wc -l)
if [[ "$DELETED" -gt 0 ]]; then
  echo "[$(date -Iseconds)] Deleted $DELETED old backup(s) (older than ${KEEP_DAYS} days)"
fi

# List recent backups
echo "[$(date -Iseconds)] Recent backups:"
ls -lht "$BACKUP_DIR"/data-*.tar.gz 2>/dev/null | head -5

echo "[$(date -Iseconds)] Backup complete."
