# Docs

- `docs/release-checklist.md`

# Release Tags

- Stable releases use `vX.Y` tags on `master` (publishes `latest` + `vX.Y`).
- Dev releases use `vX.Y.Z` tags on `dev` (publishes `dev` + `vX.Y.Z`).

# Install (Docker Compose)

## Requirements

- Docker + Docker Compose

## Create a compose.yml

Create a `compose.yml` file with the following content. You can use `dev`,
`latest`, or a pinned version tag like `v0.1.0` for the image. The `backup`
service is optional; remove it if you do not want scheduled backups.

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
    env_file: .env
    volumes:
      - pgdata:/var/lib/postgresql/data

  backup:
    image: ghcr.io/thebitbanger/kethuroth:dev
    restart: unless-stopped
    env_file: .env
    depends_on:
      - db
    volumes:
      - ./backups:/backups

volumes:
  pgdata:
```

## Environment

Create a `.env` file next to where you run docker compose:

```
# Django
DJANGO_SECRET_KEY=replace-me
DJANGO_DEBUG=false
DJANGO_ADMIN_USER=admin
DJANGO_ADMIN_PASS=admin
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8765
DJANGO_SECURE_PROXY_SSL_HEADER=true

# Postgres
POSTGRES_USER=gulgrir
POSTGRES_PASSWORD=gulgrir
POSTGRES_DB=gulgrir
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Backup
BACKUP_SCHEDULE=0 5 * * *
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_COUNT=30
BACKUP_UID=1000
BACKUP_GID=1000
TZ=UTC

# Gulgrir
GULGRIR_PORT=8765
```

Notes:
- `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASS` are used to auto-create a superuser on first run.
- Change the defaults for any real deployment.
- `GULGRIR_PORT` controls the host port that maps to container port 8765.
- `DJANGO_ALLOWED_HOSTS` should include any hostnames or IPs you use to access the app.
- `DJANGO_CSRF_TRUSTED_ORIGINS` must include the full scheme + host (and port if used).
- `DJANGO_SECURE_PROXY_SSL_HEADER` should be `true` only when running behind a reverse proxy.

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
docker compose down
docker compose pull
docker compose up -d --force-recreate
```

Migrations run automatically when the container starts.

## Access

Visit: `http://localhost:8765`

You can put a reverse proxy in front of the app if you want (not bundled here).

## Admin user

On first run, the entrypoint auto-creates a superuser using `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASS`. Use the admin user to create additional user accounts.

## Database Backup Location

Database backups are written to `./backups` on the host by the optional `backup`
service.

## Release channel

Only the dev channel is available right now. Stable releases will be added once
the first stable milestone is ready.

# Backups

The `backup` service creates `./backups` automatically, but pre-creating the
directory (and setting `BACKUP_UID` / `BACKUP_GID`) avoids root-owned files.

## Scheduled backups

The `backup` service runs backups on a schedule. Configure it with:

- `BACKUP_SCHEDULE` (cron format, default `0 5 * * *`)
- `BACKUP_RETENTION_DAYS` (default `7`)
- `BACKUP_RETENTION_COUNT` (default `30`)
- `BACKUP_UID` / `BACKUP_GID` (optional, set to your host user/group to avoid root-owned files)
- `TZ` (optional, set to your local timezone for schedule timing)

The `backup` service includes a healthcheck that uses `pg_isready` to verify
database connectivity. Check it with:

```
docker compose ps
```

To find your UID/GID:

```
id -u
id -g
```

## Docs for your version

If you are running a tagged release, use the GitHub branch switcher to select
your tag so the README matches your image version.

Note: GHCR package pages show the README from the default branch, which may not
match your pinned tag.

## On-demand backup

```
docker compose run --rm backup backup
```

# Restores

## Stop app services

```
docker compose stop app
```

If you have more services that connect to the database, stop them too. If your
version of the stack does not include a service named in newer docs, ignore it.
When in doubt, use the README that matches your image tag.

## Restore the dump

```
docker compose run --rm backup restore /backups/<dump file>.dump
```

## Start the application

```
docker compose start app
```
