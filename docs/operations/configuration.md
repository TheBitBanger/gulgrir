# Configuration

Every setting is an environment variable in `.env`, set only to override its default. At
start-up the log lists every setting, its default, your override and the value in effect;
secrets are always redacted.

## Minimal `.env`

Secrets have no default and must be set. Generate each with the command below; its output
uses only `A-Z a-z 0-9 - _`, so it is safe in `.env` unquoted:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

```
GULGRIR_SECRET_KEY=
GULGRIR_DB_PASSWORD=
```

An empty value counts as missing and stops start-up.

The first start also needs an administrator, of your own choosing. Once the superuser
exists, you can remove these two lines:

```
GULGRIR_ADMIN_USER=
GULGRIR_ADMIN_PASSWORD=
```

## Settings

| Setting                         | Old name, still accepted         | Default     | Read as |
| ------------------------------- | -------------------------------- | ----------- | ------- |
| `GULGRIR_SECRET_KEY`            | `DJANGO_SECRET_KEY`              | none, secret | At least 50 random characters; a weak one fails `check --deploy` with `security.W009`. |
| `GULGRIR_DB_PASSWORD`           | `POSTGRES_PASSWORD`              | none, secret | |
| `GULGRIR_DB_USER`               | `POSTGRES_USER`                  | `gulgrir`   | |
| `GULGRIR_DB_NAME`               | `POSTGRES_DB`                    | `gulgrir`   | |
| `GULGRIR_DB_HOST`               | `POSTGRES_HOST`                  | `db`        | |
| `GULGRIR_DB_PORT`               | `POSTGRES_PORT`                  | `5432`      | A port number |
| `GULGRIR_DEBUG`                 | `DJANGO_DEBUG`                   | `false`     | Only `true`, in any case, enables Django's debug pages and makes both apps reload when their source changes; anything else is `false`, and the start-up report notes any value other than `true` or `false` |
| `GULGRIR_ENV`                   |                                  | `dev`       | Header badge: `prod`, `production`, `live` → production; `staging`, `stage`, `preprod`, `qa` → staging; anything else → dev, noted in the start-up report |
| `GULGRIR_ALLOWED_HOSTS`         | `DJANGO_ALLOWED_HOSTS`           | empty: any host | Comma-separated hostnames or IPs used to reach the app |
| `GULGRIR_CSRF_TRUSTED_ORIGINS`  | `DJANGO_CSRF_TRUSTED_ORIGINS`    | empty       | Comma-separated full origins: scheme, host, and port if used |
| `GULGRIR_BEHIND_HTTPS_PROXY` | `DJANGO_SECURE_PROXY_SSL_HEADER` | `false` | Only `true`, in any case, trusts `X-Forwarded-Proto`; anything else is `false`, noted like `GULGRIR_DEBUG`. Set it only behind a reverse proxy that sets that header |
| `GULGRIR_ADMIN_USER`            | `DJANGO_ADMIN_USER`              | none        | Username of the superuser created when none exists; unused afterwards |
| `GULGRIR_ADMIN_PASSWORD`        | `DJANGO_ADMIN_PASS`              | none, secret | Password of that superuser; unused afterwards |
| `GULGRIR_PORT`                  |                                  | `8765`      | Host port Compose maps to the app; not read by the app |
| `GULGRIR_VERSION`               |                                  | `latest`; `dev` until the first promotion | Image tag Compose runs: `latest`, `dev` or a release `rN`, see [releasing](../development/releasing.md); not read by the app |

The database and backup services read the database settings under their old `POSTGRES_*`
names; `compose.yml` and the backup service in [backups](backups.md) map the `GULGRIR_DB_*`
settings to them.

The backup service, [kethuroth](https://github.com/TheBitBanger/kethuroth), reads `BACKUP_SCHEDULE`, `BACKUP_RETENTION_DAYS`,
`BACKUP_RETENTION_COUNT`, `BACKUP_UID`, `BACKUP_GID` and `TZ`; see [backups](backups.md).

## Behind a reverse proxy

Add the public URLs and trust the proxy's headers:

```
GULGRIR_ALLOWED_HOSTS=gulgrir.your-domain.com,your-domain.com
GULGRIR_CSRF_TRUSTED_ORIGINS=https://gulgrir.your-domain.com,http://your-domain.com:8765
GULGRIR_BEHIND_HTTPS_PROXY=true
```
