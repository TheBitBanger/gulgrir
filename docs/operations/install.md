# Install

Requires Docker with Compose.

## compose.yml

In an empty directory, download [`compose.yml`](../../compose.yml), the required stack of app
and database:

```
curl -fsSLO https://raw.githubusercontent.com/TheBitBanger/gulgrir/dev/compose.yml
```

Never edit it: an upgrade replaces it. It runs the image `GULGRIR_VERSION` names, `dev`
until the first release is promoted. To pin a release `rN`, download from `rN` instead of
`dev` and set `GULGRIR_VERSION=rN` in `.env`; [releasing](../development/releasing.md) says
what each tag means.

Anything else, such as the optional [backup service](backups.md), goes in a
`compose.override.yml` beside it, which Compose loads on its own.

## .env

Write a `.env` next to `compose.yml`, with the secrets and first administrator
[configuration](configuration.md#minimal-env) asks for. Every other setting has a default.

## Start

```
docker compose up -d
```

Visit `http://localhost:8765`. Migrations run automatically when the container starts.
`docker ps` shows the app container as unhealthy when Django stops answering; the
container keeps running, so read its log before restarting it. On
first run the entrypoint creates a superuser from `GULGRIR_ADMIN_USER` /
`GULGRIR_ADMIN_PASSWORD`, and stops if either is missing; the Django admin is an
operational fallback, not the product UI.

A reverse proxy in front is optional and not bundled; see
[configuration](configuration.md#behind-a-reverse-proxy).

## Upgrade

Download `compose.yml` again, from the same place as above, then:

```
docker compose down
docker compose pull
docker compose up -d
```

Migrations run on start. `.env` and `compose.override.yml` stay as they are; the start-up
log lists any old setting name to rename. A release that needs more than this is marked as a
breaking change, and its extra step is added here.

### Switching from a compose file copied from this guide

Earlier versions of this guide held a compose file to copy. It keeps working until the first
release after 2027-10-10, which stops accepting its `entrypoint:` and `command:` lines.
Switch once before then:

1. Move whatever you changed in your copy into `compose.override.yml`, holding only those
   changes. If you run the backup service, add it there as [backups](backups.md) shows.
2. Stop the stack with your old file: `docker compose down`.
3. If root owns `backups/`, hand it to the backup service's user, since the old copy ran
   it as root: `sudo chown -R "${BACKUP_UID:-1000}:${BACKUP_GID:-1000}" backups`, with
   the values from your `.env`.
4. Download `compose.yml` over your copy, as above, and run `docker compose up -d`.

The project name `gulgrir` and the database volume are unchanged, so your data stays.
