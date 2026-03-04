#!/usr/bin/env sh
set -e

if [ "$(id -u)" = "0" ] && [ -n "${BACKUP_UID:-}" ] && [ -n "${BACKUP_GID:-}" ] && [ -z "${BACKUP_DROP_PRIVS:-}" ]; then
  backup_dir="${BACKUP_DIR:-/backups}"
  mkdir -p "$backup_dir"
  chown "${BACKUP_UID}:${BACKUP_GID}" "$backup_dir"
  exec env BACKUP_DROP_PRIVS=1 gosu "${BACKUP_UID}:${BACKUP_GID}" "$0" "$@"
fi

command="${1:-schedule}"

case "$command" in
  backup)
    shift
    exec /app/backup/backup.sh "$@"
    ;;
  restore)
    shift
    exec /app/backup/restore.sh "$@"
    ;;
  schedule)
    exec /app/backup/cron.sh
    ;;
  *)
    echo "Usage: entrypoint.sh [backup|restore|schedule]" >&2
    exit 1
    ;;
esac
