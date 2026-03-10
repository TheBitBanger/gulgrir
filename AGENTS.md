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
- Run Django commands: `poetry run python src/manage.py <command>`
- Note: default DB host is `db`, so local commands need the Compose network or a local DB override.
- To run migrations against the Compose DB:
  - `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py migrate`
- When generating migrations, ensure the app container is running with bind mounts so new migration files are written to the host:
  - `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py makemigrations`

Environment variables:

- `.env` is used by Compose (`compose/dev.yml`)
- `DJANGO_SECRET_KEY` and `DJANGO_DEBUG` are read in `src/gulgrir/settings.py`
- Postgres vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`

## Tests

No dedicated test runner config (pytest/tox/nox) is present. Use Django's
test runner via `manage.py`.

Run all tests:

- `python src/manage.py test`
- `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py test`

Run tests for a single app:

- `python src/manage.py test tracker`
- `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py test tracker`

Run a single test module:

- `python src/manage.py test tracker.tests`
- `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py test tracker.tests`

Run a single TestCase class:

- `python src/manage.py test tracker.tests.MyTestCase`
- `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py test tracker.tests.MyTestCase`

Run a single test method:

- `python src/manage.py test tracker.tests.MyTestCase.test_something`
- `docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py test tracker.tests.MyTestCase.test_something`

If you add pytest, document `pytest -k` style single-test commands here.

## Linting and formatting

No lint/format config detected (no Ruff/Black/flake8/isort config files).
Do not assume a formatter unless one is added. Keep edits consistent with
existing style.

## Type checking

Mypy is configured in `pyproject.toml` with django-stubs:

- Plugins: `mypy_django_plugin.main`, `django-stubs`
- Django settings module: `gulgrir.settings`

Suggested type-check command (if mypy is installed):

- `mypy src`

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
