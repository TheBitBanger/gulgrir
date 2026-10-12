# 0007. The compose file maps database settings to the database and backup services

- Status: accepted
- Date: 2026-10-11

## Context

The configuration domain renames every setting to `GULGRIR_*` and keeps the old names
working (CFG-S2). The app's own settings are translated by the configuration check, inside
the app container. The database (`postgres:16`) and backup ([kethuroth](https://github.com/TheBitBanger/kethuroth))
containers are third-party images that read `POSTGRES_*` straight from their environment;
the check cannot reach them. Until now every service received the whole `.env`.

If only the app understood the new names, an install that follows the documentation and
sets `GULGRIR_DB_PASSWORD` would start a database with no password, and a fresh one refuses
to start.

## Alternatives

| Option                                                     | Rejected because                                                                 |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Keep `POSTGRES_*` as the database settings' names          | Two naming schemes in one `.env`, and the report could not flag them consistently. |
| Set `POSTGRES_*` from the app container                    | Containers do not share environments; it would need a wrapper image for Postgres. |
| Ship the compose file inside the image                     | Installs own their compose file and may run their own reverse proxy (0005).       |

## Decision

The compose file maps `GULGRIR_DB_*` to the `POSTGRES_*` names the database and backup
services read, falling back to the old names and then to the defaults, so an `.env` with
either name works. The database service no longer receives `.env`. The backup service still
does, for its own `BACKUP_*` settings.

## Consequences

- Breaking: every install edits its compose file once, replacing the database service's
  `env_file` and adding the backup service's `environment`, as shown in
  [install](../../operations/install.md). An install that keeps the old compose file and the
  old names keeps working until it renames a database setting.
- The database settings' defaults appear twice, in the configuration check and in the
  compose file, because Compose resolves them on the host before any container starts.
- The dev stack passes `--env-file .env` to Compose, since its compose files live in
  `compose/` and Compose otherwise looks for `.env` there.
