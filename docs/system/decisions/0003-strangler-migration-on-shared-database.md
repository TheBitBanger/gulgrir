# 0003. Strangler migration on a shared database

- Status: accepted
- Date: 2026-10-07

## Context

[0002](0002-typescript-full-stack.md) replaces a system that is in daily use. Losing data is
not acceptable (SYS-10). Awkward intermediate states during the move are acceptable.

## Alternatives

| Option                                     | Rejected because                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Rewrite, then copy the data over in one script | Nothing is usable until the rewrite is done, and a single mapping has to be right on cutover day. |

## Decision

The new app runs next to Django against the same PostgreSQL database. A reverse proxy routes
each path to whichever app currently serves it. Screens move over one slice at a time,
starting with metadata matching on the library.

1. **One schema owner at a time.** Django's migrations own the existing tables until
   handover. The new app reads and writes their rows, using a Drizzle schema generated from
   the database, but never changes the tables. Tables only the new app uses are owned by
   Drizzle from the start.
2. **Handover.** After the last Django screen is gone:
   - freeze Django's migrations;
   - create a starting-point Drizzle migration from the live schema;
   - remove Django.
3. **Every step is rehearsed.** Back up, restore into a copy, apply the step there, and
   compare row counts and totals. Only then apply it to the live instance.

## Consequences

- Existing passwords stay valid, because the new app verifies Django's PBKDF2 hashes.
- During the transition there are two logins and two visual styles.
- Changing an existing table needs a Django migration until handover. Prefer new tables over
  changing old ones.
- Data is never copied between databases, so there is no separate copy that could go wrong.
