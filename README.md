# Docs

- `docs/behavior-baseline.md`
- `docs/release-checklist.md`

# Release Tags

- Stable releases use `vX.Y` tags on `master` (publishes `latest` + `vX.Y`).
- Dev releases use `vX.Y.Z` tags on `dev` (publishes `dev` + `vX.Y.Z`).

# Install (Docker Compose)

## Requirements

- Docker + Docker Compose

## Create a compose.yml

Create a `compose.yml` file with the following content. You can use `dev`,
`latest`, or a pinned version tag like `v0.1.0` for the image.

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
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8765
```

Notes:
- `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASS` are used to auto-create a superuser on first run.
- Change the defaults for any real deployment.
- `GULGRIR_PORT` controls the host port that maps to container port 8765.
- `DJANGO_ALLOWED_HOSTS` should include any hostnames or IPs you use to access the app.
- `DJANGO_CSRF_TRUSTED_ORIGINS` must include the full scheme + host (and port if used).

## If using a reverse proxy

Add the public URL(s) and enable proxy headers. Example:

```
DJANGO_ALLOWED_HOSTS=gulgrir.your-domain.com,your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://gulgrir.your-domain.com,http://your-domain.com:8765
DJANGO_SECURE_PROXY_SSL_HEADER=true
```

## Start the stack

```
docker compose up -d
```

## Upgrades

To upgrade to a newer image, pull and recreate the app container:

```
docker compose pull app
docker compose up -d --force-recreate
```

Migrations run automatically when the container starts.

## Access

Visit: `http://localhost:8765`

You can put a reverse proxy in front of the app if you want (not bundled here).

## Admin user

On first run, the entrypoint auto-creates a superuser using `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASS`. Use the admin user to create additional user accounts.

## Database Backup Location

Database backups are written to `./backups` on the host (from the db container).

## Release channel

Only the dev channel is available right now. Stable releases will be added once
the first stable milestone is ready.

# Backups

## Create the `backups` directory

```
mkdir -p backups
```

## Backup the database

```
docker compose exec -T db pg_dump -U gulgrir -d gulgrir -F c > backups/gulgrir_$(date +%F_%H%M%S).dump
```

# Restores

## Start the database only

```
docker compose up -d db
```

## Restore the dump

```
cat backups/<dump file>.dump | docker compose exec -T db pg_restore -U gulgrir -d gulgrir --clean --if-exists
```

## Start the application

```
docker compose up -d app
```
