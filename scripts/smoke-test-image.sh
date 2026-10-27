#!/usr/bin/env bash
# Image smoke test: builds the release image, starts it through compose.yml on a fresh
# database, and checks it the way an install would see it. Runs on the host.
set -euo pipefail
cd "$(dirname "$0")/.."

name=gulgrir-smoke-$$
# Built under compose.yml's own image name with a local-only tag, so pinning that tag in .env
# makes compose.yml's image line resolve to it.
image=ghcr.io/thebitbanger/gulgrir:$name
port=${SMOKE_PORT:-18765}
dir=$(mktemp -d)
status=0

compose() { (cd "$dir" && docker compose -p "$name" "$@"); }

cleanup() {
  compose down -v >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
  rm -rf "$dir"
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

# As an install: compose.yml unchanged in an empty directory, beside a .env holding only
# secrets, the first superuser, the port and a pinned version (SYS-V15). The override only
# shortens the image's health-check interval, which compose.yml doesn't set.
cat >"$dir/.env" <<EOF
GULGRIR_SECRET_KEY=$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=')
GULGRIR_DB_PASSWORD=smoke
GULGRIR_ADMIN_USER=smoke
GULGRIR_ADMIN_PASSWORD=smoke-password
GULGRIR_PORT=$port
GULGRIR_VERSION=$name
EOF
cat >"$dir/compose.override.yml" <<EOF
services:
  app:
    healthcheck:
      interval: 1s
      start_period: 0s
EOF

start() { cp compose.yml "$dir/" && compose --progress quiet up -d; }
check "compose.yml, copied unchanged into an empty directory, starts the image (SYS-V15)" start
if [ $status -ne 0 ]; then
  compose logs 2>&1 || true
  exit $status
fi
app=$(compose ps -q app)

healthz() { curl -fsS "http://127.0.0.1:$port/healthz"; }
login_page() { curl -fsS -o /dev/null "http://127.0.0.1:$port/login/"; }
logs() { docker logs "$app" 2>&1; }
health() { docker inspect -f '{{.State.Health.Status}}' "$app"; }
running() { [ "$(docker inspect -f '{{.State.Running}}' "$app")" = true ]; }
is_health() { [ "$(health)" = "$1" ]; }

# Stops gunicorn's master without procps, which the slim image lacks.
kill_django() {
  docker exec "$app" python -c '
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
check "the configuration report is in the container log (SYS-V6)" sh -c "docker logs $app 2>&1 | grep -q 'IN EFFECT'"
check "gunicorn's output is in the container log (SYS-V6)" sh -c "docker logs $app 2>&1 | grep -q 'Listening at'"
check "the image's health check reports healthy (SYS-V12)" within 30 is_health healthy

kill_django || true
check "with Django dead the health check reports unhealthy (SYS-V12)" within 30 is_health unhealthy
check "with Django dead the container keeps running (SYS-V12)" running

if [ $status -ne 0 ]; then
  echo "--- container log ---"
  logs
fi
exit $status
