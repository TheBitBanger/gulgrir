# Development environment

Development runs in Docker Compose: `compose.yml`, the stack installs run, with
`compose.dev.yml` on top to build the app locally, mount the repository into it and set
`GULGRIR_DEBUG` to `true`. The dev app container builds the Dockerfile's `qa` target, which
carries the lint, type and security tools; published images build the `runtime` target. The
dev stack has no backup service. The app listens on 8765
(`GULGRIR_PORT`), and Compose reads `.env` as described in
[configuration](../operations/configuration.md).

| Task                                  | Command            |
| ------------------------------------- | ------------------ |
| Start db and app                      | `make dev-up`      |
| Start after dependency or Docker changes | `make dev-build` |

The dev container starts like an install's, through the image's entrypoint
([design](../system/design.md#start-up)): gunicorn behind the new app's front
door. Because `GULGRIR_DEBUG` is true, gunicorn reloads when a file under `src/` changes and
Node restarts when one under `app/src/` does; both are bind-mounted. A change to the
entrypoint, the Dockerfile or dependencies needs `make dev-build`.

Migrations run when the app container starts. The first start on an empty database also
creates a superuser, and stops unless `.env` sets `GULGRIR_ADMIN_USER` and
`GULGRIR_ADMIN_PASSWORD`; set both in your dev `.env`.

## Django commands

The database host is `db`, reachable only on the Compose network, so run Django commands in
the container:

```
docker compose -f compose.yml -f compose.dev.yml exec app python /app/src/manage.py <command>
```

`makemigrations` needs the bind mount so new migration files land on the host.

## Restore a production backup

A release rehearsal runs on a copy of production's data. The dumps are `pg_dump` custom
format, so the dev database container restores them itself. This replaces the dev data, so
dump it first if you want it back:

```
docker compose -f compose.yml -f compose.dev.yml exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backups/dev_pre_restore.dump
scp <prod host>:<prod install>/backups/<dump file>.dump backups/
docker compose -f compose.yml -f compose.dev.yml stop app
docker compose -f compose.yml -f compose.dev.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/<dump file>.dump
make dev-up
```

`backups/` is ignored by git. Migrations newer than the dump apply when the app starts.

## Dependencies

The new app's packages are managed with pnpm in `app/`. In the dev container they live in
their own volume over `app/node_modules`, so packages built for the host and for the
container never mix; `make check` installs them there from the lockfile.

Python dependencies are managed with Poetry on the host (`poetry install`, `poetry lock`).
Don't run Poetry inside the dev container: the bind mount exposes the host's `.venv`, and
Poetry in the container replaces it with one the host can't use.

## CSS

Tailwind compiles `src/tracker/static/tracker/css/tailwind.css` into `app.css`:

```
npm run build:css
npm run watch:css
```

Templates and static assets live under `src/tracker/templates` and `src/tracker/static`.
