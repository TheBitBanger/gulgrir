#!/usr/bin/env sh
set -e

python /app/src/manage.py migrate --noinput
python /app/src/manage.py createsuperuser_if_none

exec "$@"
