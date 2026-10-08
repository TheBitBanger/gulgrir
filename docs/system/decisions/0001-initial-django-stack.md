# 0001. Initial stack: Django, server-rendered templates, PostgreSQL

- Status: superseded by [0002](0002-typescript-full-stack.md)
- Date: 2025-06 (recorded 2026-10-07)

## Context

Gulgrir began in mid-2025 as a personal tool, built to iterate quickly. The original
planning documents set the first stack:

- Django, for fast iteration and its admin as a temporary UI.
- PostgreSQL.
- Docker Compose for distribution.
- Celery and Redis for background jobs.
- A monolith with scheduled polling for metadata.

## Alternatives

FastAPI or Flask with a separate SPA (React, Vue or Svelte), with the job queue being RQ or
cron instead of Celery.

## Decision

Django 5 with server-rendered templates, later extended with HTMX and Tailwind. PostgreSQL,
and one app image plus a database container in Docker Compose. Celery and Redis were never
adopted, because no background work was ever built.

## Consequences

- The admin got the app working quickly, but the custom UI became raw HTML and CSS with no
  component model, so styles drifted and widgets broke.
- HTML forms only send GET and POST, which spread actions over many POST endpoints.
- Python's type hints are not enforced, and Django's ORM resists type checkers, so typing
  gave little protection.
- Screens pulled raw rows and added them up in templates, so time dashboards meant large
  payloads.
- Automatic metadata fetching (MET-1) was never built.
