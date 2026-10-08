# 0002. TypeScript full stack on PostgreSQL

- Status: accepted
- Date: 2026-10-07
- Supersedes: [0001](0001-initial-django-stack.md)

## Context

The consequences of [0001](0001-initial-django-stack.md) are now the main cost of working on
gulgrir. The requirements add needs that stack serves poorly:

- automatic metadata matching with background refresh (MET-1, MET-3)
- desktop and phone use (SYS-7)
- charts and metrics (SYS-8, TIM-4)

One developer maintains it, with heavy use of coding agents.

## Alternatives

| Option                                    | Rejected because                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------- |
| Python: FastAPI, Pydantic, SQLAlchemy 2, plus an SPA | Types are still unenforced, and it means two languages anyway.          |
| Go API plus a TypeScript UI               | Two languages joined by a generated contract, which keeps the API/UI disconnect. |
| SvelteKit                                 | Smaller component and chart ecosystem.                                          |
| Next.js                                   | Its caching and server-component model add complexity a VPN-only app doesn't need. |
| A job queue (pg-boss, Celery with Redis)  | A job duplicates state its row already holds, and the two copies drift apart. Every background need in the requirements already has a row that says whether work is due. |

## Decision

TypeScript in strict mode for the server and the UI, running on Node LTS, with PostgreSQL
kept.

| Layer          | Choice                                           |
| -------------- | ------------------------------------------------ |
| API            | Hono, with Zod schemas at every boundary         |
| Database access | Drizzle                                         |
| Background work | Workers that query the rows needing work; no queue |
| UI             | React with Vite, shadcn/ui on Tailwind           |
| Routing and data | TanStack Router and TanStack Query             |
| Tables and charts | TanStack Table and Recharts                   |
| Tests          | Vitest, with Testcontainers for PostgreSQL       |

One image serves the API and the built UI. It deploys next to PostgreSQL and the existing
backup container. Endpoints return data shaped for the screen that uses it. Aggregation
happens in SQL, not in the client.

Background work, such as metadata refresh, imports and notifications, is done by worker loops.
Each loop queries for rows whose own state says work is due, processes them, and records the
outcome on the same row. A crashed or restarted worker finds the same rows again, so nothing
needs reconciling. The loops start inside the app process. If more than one worker is ever
needed, `FOR UPDATE SKIP LOCKED` lets them claim rows without colliding. Each domain's
specification defines the state that decides when work is due.

## Consequences

- Types are shared from the database through the API to the UI, and the compiler enforces
  them.
- The REST API uses the full set of HTTP verbs and describes itself, so the *arr-style
  integrations and any future clients can use it.
- Background work needs no infrastructure beyond PostgreSQL, which keeps installation simple
  (SYS-4). There is no job state to reconcile.
- Rows that carry background work need an index on the columns that decide when work is due.
- The npm supply chain becomes a risk. Mitigations: a committed lockfile, a minimum release
  age for new versions, and a short dependency list.
- The specific libraries are young and may be replaced; the layers will outlast them.
- Moving from the running Django system follows
  [0003](0003-strangler-migration-on-shared-database.md).
