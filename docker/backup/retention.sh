#!/usr/bin/env sh
set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-30}"

if [ ! -d "$BACKUP_DIR" ]; then
  exit 0
fi

if [ "$RETENTION_DAYS" -gt 0 ] 2>/dev/null; then
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "*.dump" -mtime "+$RETENTION_DAYS" -print0 | xargs -0r rm -f
fi

if [ "$RETENTION_COUNT" -gt 0 ] 2>/dev/null; then
  files="$(ls -1t "$BACKUP_DIR"/*.dump 2>/dev/null || true)"
  if [ -n "$files" ]; then
    count=0
    for file in $files; do
      count=$((count + 1))
      if [ "$count" -gt "$RETENTION_COUNT" ]; then
        rm -f "$file"
      fi
    done
  fi
fi
