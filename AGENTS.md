# AGENTS.md

This file orients coding agents to the conventions and commands used in this
repository. It is tailored to this codebase; if you add new tooling, update
this document.

## Repository overview

- Framework: Django 5.2 (Python 3.11+)
- App package: `src/tracker`
- Project config: `src/gulgrir`
- Entrypoint: `src/manage.py`
- Docker Compose: `compose/dev.yml`, `compose/dev.bind.yml`
- Database: PostgreSQL (container `db` in Compose)

## Rules from other agent configs

- No Cursor rules found: no `.cursorrules` or `.cursor/rules/*` present.
- No Copilot rules found: no `.github/copilot-instructions.md` present.

## Build, run, and environment

Local dev uses Docker Compose. The app container runs Django and depends on
PostgreSQL. The dev Compose file wires ports and env vars.

Common commands (run from repo root):

- Start database only (dev, with bind mounts):
  - `docker compose -f compose/dev.yml -f compose/dev.bind.yml up -d db`
- Start app + db:
  - `docker compose -f compose/dev.yml -f compose/dev.bind.yml up -d`
- Run the app (inside container via compose entrypoint):
  - `python /app/src/manage.py runserver 0.0.0.0:8765`
- Migrations are applied in container entrypoint:
  - `python /app/src/manage.py migrate --noinput`
- A superuser is auto-created in container entrypoint:
  - `python /app/src/manage.py createsuperuser_if_none`

Local virtualenv workflow (Poetry):

- Enter shell: `poetry shell`
- Run one-off Django commands: `poetry run python src/manage.py <command>`
- Do not use Poetry commands for test/QA execution; use Make targets below.
- Note: default DB host is `db`, so local commands need the Compose network or a local DB override.
- To run migrations against the Compose DB:
  - `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py migrate`
- When generating migrations, ensure the app container is running with bind mounts so new migration files are written to the host:
  - `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py makemigrations`

Frontend CSS (Tailwind, compiled):

- Build CSS once:
  - `npm run build:css`
- Watch CSS during dev:
  - `npm run watch:css`

Environment variables:

- `.env` is used by Compose (`compose/dev.yml`)
- `DJANGO_SECRET_KEY` and `DJANGO_DEBUG` are read in `src/gulgrir/settings.py`
- Postgres vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`

## Tests

Use Make targets for test/QA execution. Prefer containerized commands to avoid
host-env DB/network drift.

Run all tests:

- `make test`

Run a single app/module/class/method:

- `make test-label TEST=tracker`
- `make test-label TEST=tracker.tests`
- `make test-label TEST=tracker.tests.MyTestCase`
- `make test-label TEST=tracker.tests.MyTestCase.test_something`

If you add pytest, document `pytest -k` style single-test commands here.

## Linting and formatting

Use containerized QA commands from repo root:

- `make qa-quick`
- `make qa-full`

`qa-quick` runs Ruff lint + format checks and mypy.
`qa-full` runs Ruff, mypy, basedpyright, Bandit, pip-audit, gitleaks
(staged changes), and `manage.py check --deploy`.

Agent default verification policy:

- Use `make qa-quick` for normal validation after most code changes.
- Use `make qa-full` for deep/thorough validation or cross-cutting changes.
- Do not run tests/QA via `poetry run ...` unless the user explicitly asks.

## Type checking

Mypy is configured in `pyproject.toml` with django-stubs:

- Plugins: `mypy_django_plugin.main`
- Django settings module: `gulgrir.settings`

Basedpyright is configured via `pyrightconfig.json`.

Suggested type-check commands:

- `make qa-quick` (includes mypy)
- `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app basedpyright`

## Code style guidelines (inferred from codebase)

### Imports

- Use standard library imports first, then third-party, then local imports.
- Prefer explicit imports (no wildcard imports).
- Local imports often use relative paths within an app (e.g. `from .models`).

### Formatting

- Keep line lengths reasonable; existing code uses multi-line argument lists.
- Use 4-space indentation, no tabs.
- Keep docstrings for non-obvious logic or public APIs.

### Types and typing patterns

- Type hints are used in services and actions (`TypedDict`, `Protocol`).
- Use `QuerySet[Model]` generics where relevant.
- Prefer `str | None` style unions (Python 3.11+).

### Naming conventions

- Classes: `PascalCase` (e.g. `UserItem`, `QueueCreate`).
- Functions/methods/variables: `snake_case`.
- Constants and enums: `UPPER_CASE` or `Enum`/`TextChoices` subclasses.
- Django model fields follow snake_case names.

### Django patterns

- Use class-based views for CRUD flows, function views for lightweight routes.
- Use `LoginRequiredMixin` or `@login_required` for authenticated endpoints.
- Use `get_object_or_404` for object lookups scoped to the user.
- Use QuerySets with `.select_related()` / `.prefetch_related()` for efficiency.
- Use `Q` objects to compose filters and keep business logic in services.

### Error handling and HTTP responses

- For bad requests, return `HttpResponseBadRequest` or JSON with status 400.
- Validate POST inputs and guard against missing required fields.
- Catch `IntegrityError` around unique constraints and race conditions.

### Data and DB writes

- Use `transaction.atomic()` for multi-step operations that must be consistent.
- Use `bulk_create` where appropriate to avoid per-row overhead.

### JSON and request handling

- Accept JSON or form-encoded input depending on endpoint; detect via
  `Content-Type` header.
- For HTMX endpoints, return partial templates or JSON responses as needed.

### Logging / debug output

- Current code uses `print(..., file=sys.stderr, flush=True)` for debug.
- Prefer structured logging if/when a logging setup is added.

## Repo-specific notes

- Templates and static assets live under `src/tracker/templates` and
  `src/tracker/static`.
- Compose uses `compose/dev.bind.yml` to mount `src/` into the container.
- The app runs on port `8765` by default (`GULGRIR_PORT` env var).

## When adding new tooling

- Update this file with new commands and style rules.
- If you add formatters/linters, include single-file and single-test examples.

## Testing expectations for agents

- Add tests when coverage is missing for the change.
- Run tests after every change:
  - Small/localized changes: run scoped checks with `make test-label ...` and/or `make qa-quick`.
  - Multi-module or risky changes: run `make qa-full`.
  - When in doubt, prefer `make qa-quick` at minimum.
