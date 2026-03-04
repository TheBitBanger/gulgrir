#!/usr/bin/env sh
set -e

if [ -z "${1:-}" ]; then
  echo "Usage: restore.sh /backups/<dump>.dump" >&2
  exit 1
fi

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

dump_path="$1"

if [ ! -f "$dump_path" ]; then
  echo "Dump file not found: $dump_path" >&2
  exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

psql \
  -h "$POSTGRES_HOST" \
  -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();"

pg_restore \
  -h "$POSTGRES_HOST" \
  -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --clean \
  --if-exists \
  "$dump_path"

echo "Restore completed from $dump_path"
