#!/usr/bin/env bash
# Image smoke test: builds the release image, starts it with its defaults on a fresh
# database, and checks it the way an install would see it. Runs on the host.
set -euo pipefail
cd "$(dirname "$0")/.."

name=gulgrir-smoke-$$
image=$name:latest
port=${SMOKE_PORT:-18765}
status=0

cleanup() {
  docker rm -f -v "$name-app" "$name-db" >/dev/null 2>&1 || true
  docker network rm "$name" >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
}
trap cleanup EXIT

check() {
  local what=$1
  shift
  if "$@"; then
    printf '[PASS] %s\n' "$what"
  else
    printf '[FAIL] %s\n' "$what"
    status=1
  fi
}

# Retries a command once a second for up to $1 seconds.
within() {
  local seconds=$1
  shift
  for _ in $(seq "$seconds"); do
    "$@" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

docker build -q -f docker/app/Dockerfile --target runtime -t "$image" . >/dev/null
docker network create "$name" >/dev/null
docker run -d --rm --name "$name-db" --network "$name" --network-alias db \
  -e POSTGRES_USER=gulgrir -e POSTGRES_DB=gulgrir -e POSTGRES_PASSWORD=smoke \
  postgres:16 >/dev/null

# No entrypoint or command: the image's own defaults (SYS-V1). Only secrets and the first
# superuser are given, as an install's .env would.
docker run -d --name "$name-app" --network "$name" -p "$port:8765" \
  --health-interval=1s --health-start-period=0s \
  -e GULGRIR_SECRET_KEY="$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=')" \
  -e GULGRIR_DB_PASSWORD=smoke \
  -e GULGRIR_ADMIN_USER=smoke -e GULGRIR_ADMIN_PASSWORD=smoke-password \
  "$image" >/dev/null

healthz() { curl -fsS "http://127.0.0.1:$port/healthz"; }
login_page() { curl -fsS -o /dev/null "http://127.0.0.1:$port/login/"; }
logs() { docker logs "$name-app" 2>&1; }
health() { docker inspect -f '{{.State.Health.Status}}' "$name-app"; }
running() { [ "$(docker inspect -f '{{.State.Running}}' "$name-app")" = true ]; }
is_health() { [ "$(health)" = "$1" ]; }

# Stops gunicorn's master without procps, which the slim image lacks.
kill_django() {
  docker exec "$name-app" python -c '
import os, signal
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
    except OSError:
        continue
    if int(pid) != os.getpid() and any(b"gunicorn" in part for part in cmd):
        os.kill(int(pid), signal.SIGKILL)
'
}

check "the new app answers /healthz on the mapped port (SYS-V1)" within 90 healthz
check "Django answers through the front door (SYS-V2)" login_page
check "the configuration report is in the container log (SYS-V6)" sh -c "docker logs $name-app 2>&1 | grep -q 'IN EFFECT'"
check "gunicorn's output is in the container log (SYS-V6)" sh -c "docker logs $name-app 2>&1 | grep -q 'Listening at'"
check "the image's health check reports healthy (SYS-V12)" within 30 is_health healthy

kill_django || true
check "with Django dead the health check reports unhealthy (SYS-V12)" within 30 is_health unhealthy
check "with Django dead the container keeps running (SYS-V12)" running

if [ $status -ne 0 ]; then
  echo "--- container log ---"
  logs
fi
exit $status
