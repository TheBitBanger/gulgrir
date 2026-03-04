FROM postgres:16

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gosu \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /usr/local/bin/supercronic \
    https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64 \
    && chmod +x /usr/local/bin/supercronic

WORKDIR /app

COPY docker/backup/entrypoint.sh /app/backup/entrypoint.sh
COPY docker/backup/backup.sh /app/backup/backup.sh
COPY docker/backup/restore.sh /app/backup/restore.sh
COPY docker/backup/retention.sh /app/backup/retention.sh
COPY docker/backup/cron.sh /app/backup/cron.sh

RUN chmod +x /app/backup/*.sh

ENV BACKUP_DIR=/backups
ENV BACKUP_RETENTION_DAYS=7
ENV BACKUP_RETENTION_COUNT=30
ENV BACKUP_SCHEDULE="0 5 * * *"
ENV TZ=UTC

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD pg_isready -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" || exit 1

ENTRYPOINT ["/app/backup/entrypoint.sh"]
CMD ["schedule"]
