#!/usr/bin/env sh
set -e

SCHEDULE="${BACKUP_SCHEDULE:-0 5 * * *}"
cron_file="/tmp/backup.cron"

cat <<EOF > "$cron_file"
$SCHEDULE /app/backup/backup.sh
EOF

exec /usr/local/bin/supercronic "$cron_file"
