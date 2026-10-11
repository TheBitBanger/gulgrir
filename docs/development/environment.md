# Development environment

Development runs in Docker Compose: `compose/dev.yml` for the stack, `compose/dev.bind.yml`
to mount the repository into the app container and run Django's dev server. The dev app
container builds the Dockerfile's `qa` target, which carries the lint, type and security
tools; published images build the `runtime` target. The app listens on 8765
(`GULGRIR_PORT`), and Compose reads `.env` as described in
[configuration](../operations/configuration.md).

| Task                                  | Command            |
| ------------------------------------- | ------------------ |
| Start db and app                      | `make dev-up`      |
| Start after dependency or Docker changes | `make dev-build` |
| Run the scheduled backup service too  | `docker compose -f compose/dev.yml --profile backup up -d` |

Migrations run, and a superuser is created, when the app container starts.

## Django commands

The database host is `db`, reachable only on the Compose network, so run Django commands in
the container:

```
docker compose -f compose/dev.yml -f compose/dev.bind.yml exec app python /app/src/manage.py <command>
```

`makemigrations` needs the bind mount so new migration files land on the host.

## Dependencies

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
