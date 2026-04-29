SHELL := /bin/bash
.ONESHELL:

COMPOSE := docker compose -f compose/dev.yml -f compose/dev.bind.yml
APP_EXEC := $(COMPOSE) exec -T -w /workspace app
APP_MANAGE := $(APP_EXEC) python /app/src/manage.py

.PHONY: dev-build dev-up test test-label qa qa-quick qa-ui qa-full

dev-build:
	$(COMPOSE) up -d --build db app

dev-up:
	$(COMPOSE) up -d db app

test: dev-up
	$(APP_MANAGE) test

test-label: dev-up
	$(APP_MANAGE) test $(TEST)

qa: qa-full

qa-quick: dev-up
	$(APP_EXEC) ruff check src
	$(APP_EXEC) ruff format --check src
	$(APP_EXEC) mypy src

qa-ui: dev-up
	$(APP_EXEC) djlint src/tracker/templates --lint
	$(APP_EXEC) stylelint "src/tracker/templates/**/*.html" "src/tracker/static/**/*.css"

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
	run_check_soft() {
	  local name="$$1"
	  shift
	  printf "\n==> %s\n" "$$name"
	  if "$$@"; then
	    printf "[PASS] %s\n" "$$name"
	  else
	    rc=$$?
	    printf "[WARN] %s (non-blocking, exit %s)\n" "$$name" "$$rc"
	  fi
	}
	run_check "ruff check" $(APP_EXEC) ruff check src
	run_check "ruff format --check" $(APP_EXEC) ruff format --check src
	run_check "mypy" $(APP_EXEC) mypy src
	run_check "djlint" $(APP_EXEC) djlint src/tracker/templates --lint
	run_check "stylelint" $(APP_EXEC) stylelint "src/tracker/templates/**/*.html" "src/tracker/static/**/*.css"
	run_check_soft "basedpyright" $(APP_EXEC) basedpyright
	run_check_soft "bandit" $(APP_EXEC) bandit -q -r src -c /workspace/pyproject.toml
	run_check_soft "pip-audit" $(APP_EXEC) pip-audit
	run_check_soft "npm audit" $(APP_EXEC) npm audit
	run_check "gitleaks (staged)" sh -lc 'git diff --cached -- . | $(APP_EXEC) gitleaks stdin --no-banner --redact --config /workspace/.gitleaks.toml'
	run_check "django check --deploy" $(APP_EXEC) env DJANGO_DEBUG=false python /app/src/manage.py check --deploy
	if [[ $$status -ne 0 ]]; then
	  printf "\nQA full completed with failures\n"
	  exit 1
	fi
	printf "\nQA full completed successfully\n"
