# Install

Requires Docker with Compose.

## compose.yml

Use `latest`, `dev`, or a pinned tag for the image; see
[releasing](../development/releasing.md) for what each means. The `backup` service is
optional.

```yaml
name: gulgrir
services:
  app:
    image: ghcr.io/thebitbanger/gulgrir:dev
    restart: unless-stopped
    env_file: .env
    ports:
      - "${GULGRIR_PORT-8765}:8765"
    depends_on:
      - db
    entrypoint: ["/app/docker/app/entrypoint.sh"]
    command: "gunicorn gulgrir.wsgi:application --bind 0.0.0.0:8765 --workers 2"

  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${GULGRIR_DB_USER:-${POSTGRES_USER:-gulgrir}}
      POSTGRES_PASSWORD: ${GULGRIR_DB_PASSWORD:-${POSTGRES_PASSWORD:-}}
      POSTGRES_DB: ${GULGRIR_DB_NAME:-${POSTGRES_DB:-gulgrir}}
    volumes:
      - pgdata:/var/lib/postgresql/data

  backup:
    image: ghcr.io/thebitbanger/kethuroth:v0.1.1
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_USER: ${GULGRIR_DB_USER:-${POSTGRES_USER:-gulgrir}}
      POSTGRES_PASSWORD: ${GULGRIR_DB_PASSWORD:-${POSTGRES_PASSWORD:-}}
      POSTGRES_DB: ${GULGRIR_DB_NAME:-${POSTGRES_DB:-gulgrir}}
      POSTGRES_HOST: ${GULGRIR_DB_HOST:-${POSTGRES_HOST:-db}}
      POSTGRES_PORT: ${GULGRIR_DB_PORT:-${POSTGRES_PORT:-5432}}
    depends_on:
      - db
    volumes:
      - ./backups:/backups

volumes:
  pgdata:
```

## .env

Write a `.env` next to `compose.yml`; [configuration](configuration.md) lists every
variable.

## Start

```
docker compose up -d
```

Visit `http://localhost:8765`. Migrations run automatically when the container starts. On
first run the entrypoint creates a superuser from `GULGRIR_ADMIN_USER` /
`GULGRIR_ADMIN_PASSWORD`, and stops if either is missing; the Django admin is an
operational fallback, not the product UI.

A reverse proxy in front is optional and not bundled; see
[configuration](configuration.md#behind-a-reverse-proxy).

## Upgrade

```
docker compose down
docker compose pull
docker compose up -d --force-recreate
```

Migrations run on start.

### Upgrading a compose file whose `db` service has `env_file`

Settings were renamed to `GULGRIR_*`
([0007](../system/decisions/0007-compose-maps-database-settings.md)). Before pulling, replace
the `db` service's `env_file: .env` with its `environment:` block above, and add the same
block, with `POSTGRES_HOST` and `POSTGRES_PORT`, to the `backup` service. Your `.env` keeps
working as it is; the start-up log lists each old name to rename.
