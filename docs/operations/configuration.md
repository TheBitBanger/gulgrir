# Configuration

Every setting is an environment variable in `.env`, read by Compose.

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
GULGRIR_ENV=dev
```

Change every default for a real deployment.

| Variable                          | Meaning                                                                                       |
| --------------------------------- | --------------------------------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`               | Long random value, at least 50 characters, kept out of version control. A weak one fails `check --deploy` with `security.W009`. |
| `DJANGO_ADMIN_USER` / `_PASS`     | Superuser created on first run, for admin fallback access.                                    |
| `DJANGO_ALLOWED_HOSTS`            | Every hostname or IP used to reach the app.                                                   |
| `DJANGO_CSRF_TRUSTED_ORIGINS`     | Full origins: scheme, host, and port if used.                                                  |
| `DJANGO_SECURE_PROXY_SSL_HEADER`  | `true` only behind a reverse proxy that sets `X-Forwarded-Proto`.                             |
| `GULGRIR_PORT`                    | Host port mapped to the container's 8765.                                                     |
| `GULGRIR_ENV`                     | Environment badge in the header: `dev`, `staging` or `production` (aliases such as `prod`, `stage`, `qa`, `live` are accepted). |
| `BACKUP_*`                        | Only matter when the backup service runs; see [backups](backups.md).                          |

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Behind a reverse proxy

Add the public URLs and trust the proxy's headers:

```
DJANGO_ALLOWED_HOSTS=gulgrir.your-domain.com,your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://gulgrir.your-domain.com,http://your-domain.com:8765
DJANGO_SECURE_PROXY_SSL_HEADER=true
```
