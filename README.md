# Docs

- `docs/behavior-baseline.md`
- `docs/release-checklist.md`

# Install (Current Compose Setup)

This documents the current behavior using `compose/prod.yml` + `compose/local.yml`.

## Requirements

- Docker + Docker Compose

## Create a compose.yml

Create a `compose.yml` file with the following content:

```yaml
name: gulgrir
services:
  app:
    image: ghcr.io/org/media:latest
    restart: unless-stopped
    env_file: .env
    ports:
      - "${GULGRIR_PORT-8765}:8765"
    depends_on:
      - db
    entrypoint: ["/app/docker/scripts/entrypoint.sh"]
    command: "gunicorn gulgrir.wsgi:application --bind 0.0.0.0:8765 --workers 2"

  db:
    image: postgres:16
    restart: unless-stopped
    env_file: .env
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backups:/backups

volumes:
  pgdata:
```

## Environment

Create a `.env` file next to where you run docker compose:

```
DJANGO_SECRET_KEY=replace-me
DJANGO_DEBUG=false
DJANGO_ADMIN_USER=admin
DJANGO_ADMIN_PASS=admin
POSTGRES_USER=gulgrir
POSTGRES_PASSWORD=gulgrir
GULGRIR_PORT=8765
```

Notes:
- `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASS` are used to auto-create a superuser on first run.
- Change the defaults for any real deployment.
- `GULGRIR_PORT` controls the host port that maps to container port 8765.

## Start the stack

```
docker compose -f compose/prod.yml -f compose/local.yml up -d
```

## Access

Visit: `http://localhost:8765`

You can put a reverse proxy in front of the app if you want (not bundled here).

## Admin user

On first run, the entrypoint auto-creates a superuser using `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASS`. Use the admin user to create additional user accounts.

## Database Backup Location

Database backups are written to `./backups` on the host (from the db container).

# Backups

## Create the `backups` directory

```
mkdir -p backups
```

## Backup the database

```
docker compose -f compose/prod.yml -f compose/local.yml exec -T db pg_dump -U gulgrir -d gulgrir -F c > backups/gulgrir_$(date +%F_%H%M%S).dump
```

# Restores

## Start the database only

```
docker compose -f compose/prod.yml -f compose/local.yml up -d db
```

## Restore the dump

```
cat backups/<dump file>.dump | docker compose -f compose/prod.yml -f compose/local.yml exec -T db pg_restore -U gulgrir -d gulgrir --clean --if-exists
```

## Start the application

```
docker compose -f compose/prod.yml -f compose/local.yml up -d app
```
