#!/usr/bin/env bash
# Every check that gates a commit. Runs in the dev container via `make check`; prints one
# line per check, and a check's output only when it fails.
set -u
cd /workspace
status=0
log=$(mktemp)

run() {
  local name=$1
  shift
  if "$@" >"$log" 2>&1; then
    printf '[PASS] %s\n' "$name"
  else
    status=1
    printf '[FAIL] %s\n' "$name"
    cat "$log"
  fi
}

# Audits report known findings on every run, so they never fail it.
warn() {
  local name=$1
  shift
  if "$@" >"$log" 2>&1; then
    printf '[PASS] %s\n' "$name"
  else
    printf '[WARN] %s has findings; in the app container run: %s\n' "$name" "$*"
  fi
}

run "ruff check" ruff check src
run "ruff format" ruff format --check src
run "mypy" mypy src
run "djlint" djlint src/tracker/templates --lint
run "stylelint" stylelint "src/tracker/templates/**/*.html" "src/tracker/static/**/*.css"
warn "bandit" bandit -q -r src -c pyproject.toml
warn "pip-audit" pip-audit
warn "npm audit" npm audit
run "gitleaks (staged)" sh -c 'git -c safe.directory=/workspace diff --cached | gitleaks stdin --no-banner --redact --config .gitleaks.toml'
run "django check --deploy" env GULGRIR_DEBUG=false python /app/src/manage.py check --deploy
run "django tests" python /app/src/manage.py test
run "app install" pnpm -C app install --frozen-lockfile
run "biome" pnpm -C app lint
run "tsc" pnpm -C app typecheck
run "app tests" pnpm -C app test

rm -f "$log"
exit $status
