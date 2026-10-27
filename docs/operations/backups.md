# Backups and restores

The backup service is optional, so `compose.yml` doesn't hold it. It runs the standalone
[kethuroth](https://github.com/TheBitBanger/kethuroth) image, which documents every option,
and writes database dumps to `./backups` on the host.

## Turn it on

Add it to `compose.override.yml`, beside `compose.yml`:

```yaml
services:
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
    user: "${BACKUP_UID:-1000}:${BACKUP_GID:-1000}"
    volumes:
      - ./backups:/backups
```

It runs as `BACKUP_UID`:`BACKUP_GID`, 1000:1000 unless `.env` sets them. Create `backups/`
owned by that user before starting it: Docker creates a missing one owned by root, and the
service can't write to it. Then `docker compose up -d`.

## Back up now

```
docker compose run --rm backup backup
```

## Restore

Stop the app, and any other service that connects to the database:

```
docker compose stop app
```

Restore the dump, then start the app:

```
docker compose run --rm backup restore /backups/<dump file>.dump
docker compose start app
```

If a service named here doesn't exist in your version of the stack, skip it; the docs at
your image's tag match your stack.
