# 0008. Django reads the new setting names, falling back to the old ones

- Status: accepted
- Date: 2026-10-12

## Context

The configuration check renames every setting to `GULGRIR_*` and, at start-up, handed
Django each value under the old name Django read (`DJANGO_*`, `POSTGRES_*`), exported in
the entrypoint's shell. A Django command run by hand with `docker exec` or `compose exec`
skips the entrypoint, so on an `.env` written with the new names Django fell back to its
defaults and could not reach the database.

## Alternatives

| Option                                                             | Rejected because                                                                             |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| A command in the image that runs the check, then `manage.py`       | Adds an operator command nobody needs; nothing in the operations docs runs `manage.py`.      |
| Only the image smoke test runs the check before `manage.py`        | Hides the failure in the test and leaves every hand-run command broken.                      |
| Django reads only the new names                                    | A hand-run command on an `.env` still using the old names silently uses defaults, during a deprecation period that promises old names keep working. |

## Decision

Django reads each setting it already uses from its `GULGRIR_*` name, else its old name,
else its default, an empty value counting as unset. At start-up the check hands Django
every setting under the new name, already resolved, so the fallback matters only outside
start-up. Django gains no new settings; every setting added from now on belongs to the new
app.

## Consequences

- A hand-run Django command sees the same settings as start-up, whichever names `.env`
  uses.
- The old names and Django's defaults appear twice, in the check and in Django's settings.
  Both copies go when the old names are dropped.
