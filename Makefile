SHELL := /bin/bash
.ONESHELL:

COMPOSE := docker compose -f compose/dev.yml -f compose/dev.bind.yml
APP_EXEC := $(COMPOSE) exec -T -w /workspace app
APP_MANAGE := $(APP_EXEC) python /app/src/manage.py

.PHONY: dev-build dev-up test qa qa-quick qa-full qa-full-local

dev-build:
	$(COMPOSE) up -d --build db app

dev-up:
	$(COMPOSE) up -d db app

test: dev-up
	$(APP_MANAGE) test

qa: qa-full

qa-quick: dev-up
	$(APP_EXEC) ruff check src
	$(APP_EXEC) ruff format --check src
	$(APP_EXEC) mypy src

qa-full: dev-up
	status=0
	run_check() {
	  local name="$$1"
	  shift
	  printf "\n==> %s\n" "$$name"
	  if "$$@"; then
	    printf "[PASS] %s\n" "$$name"
	  else
	    rc=$$?
	    status=1
	    printf "[FAIL] %s (exit %s)\n" "$$name" "$$rc"
	  fi
	}
	run_check "ruff check" $(APP_EXEC) ruff check src
	run_check "ruff format --check" $(APP_EXEC) ruff format --check src
	run_check "mypy" $(APP_EXEC) mypy src
	run_check "basedpyright" $(APP_EXEC) basedpyright
	run_check "bandit" $(APP_EXEC) bandit -q -r src
	run_check "pip-audit" $(APP_EXEC) pip-audit
	run_check "gitleaks (staged)" $(APP_EXEC) sh -lc 'git -C /workspace diff --staged -- . | gitleaks stdin --no-banner --redact --config /workspace/.gitleaks.toml'
	run_check "django check --deploy" $(APP_EXEC) env DJANGO_DEBUG=false python /app/src/manage.py check --deploy
	if [[ $$status -ne 0 ]]; then
	  printf "\nQA full completed with failures\n"
	  exit 1
	fi
	printf "\nQA full completed successfully\n"

qa-full-local:
	status=0
	run_check() {
	  local name="$$1"
	  shift
	  printf "\n==> %s\n" "$$name"
	  if "$$@"; then
	    printf "[PASS] %s\n" "$$name"
	  else
	    rc=$$?
	    status=1
	    printf "[FAIL] %s (exit %s)\n" "$$name" "$$rc"
	  fi
	}
	run_check "ruff check" poetry run ruff check src
	run_check "ruff format --check" poetry run ruff format --check src
	run_check "mypy" poetry run mypy src
	run_check "basedpyright" poetry run basedpyright
	run_check "bandit" poetry run bandit -q -r src
	run_check "pip-audit" poetry run pip-audit
	run_check "gitleaks (staged)" bash -lc 'if command -v gitleaks >/dev/null 2>&1; then git diff --staged -- . | gitleaks stdin --no-banner --redact --config .gitleaks.toml; else git diff --staged -- . | docker run --rm -i -v "'"$$PWD"'":/repo -w /repo ghcr.io/gitleaks/gitleaks:latest stdin --no-banner --redact --config .gitleaks.toml; fi'
	run_check "django check --deploy" bash -lc 'DJANGO_DEBUG=false poetry run python src/manage.py check --deploy'
	if [[ $$status -ne 0 ]]; then
	  printf "\nLocal QA full completed with failures\n"
	  exit 1
	fi
	printf "\nLocal QA full completed successfully\n"
