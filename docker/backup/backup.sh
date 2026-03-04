#!/usr/bin/env sh
set -e

lock_dir="/tmp/backup.lock"

if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "Another backup or restore is running." >&2
  exit 1
fi

cleanup() {
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-gulgrir}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_PREFIX="${BACKUP_PREFIX:-$POSTGRES_DB}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%F_%H%M%S)"
backup_file="${BACKUP_DIR}/${BACKUP_PREFIX}_${timestamp}.dump"

export PGPASSWORD="$POSTGRES_PASSWORD"

pg_dump \
  -h "$POSTGRES_HOST" \
  -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -F c \
  -f "$backup_file"

echo "Backup written to $backup_file"

/app/backup/retention.sh
