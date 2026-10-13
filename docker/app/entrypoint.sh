#!/usr/bin/env sh
# Start-up order: docs/system/design.md.
set -e

if [ $# -gt 0 ]; then
  echo "Ignoring the command \"$*\": the image starts both apps itself. The entrypoint: and command: lines in your compose file are deprecated and can be removed." >&2
fi

settings=$(node /app/app/src/config.ts)
eval "$settings"

for _ in $(seq 30); do
  python /app/src/manage.py shell -c "from django.db import connection; connection.ensure_connection()" >/dev/null 2>&1 && break
  echo "Waiting for the database" >&2
  sleep 2
done
python /app/src/manage.py migrate --noinput
python /app/src/manage.py createsuperuser_if_none

reload=
watch=
if [ "$GULGRIR_DEBUG" = true ]; then
  reload=--reload
  watch=--watch
fi

gunicorn gulgrir.wsgi:application --bind 127.0.0.1:8000 --workers 2 $reload &
exec node $watch /app/app/src/front-door.ts 8765 http://127.0.0.1:8000
