FROM python:3.12-slim AS base

LABEL org.opencontainers.image.description="Docs: use the GitHub branch switcher to select your tag for the matching README."

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==2.0.0"

WORKDIR /app
# Only copy these files for better layer caching, when only the application code changes
COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false


FROM base AS runtime-deps
# Install runtime dependencies only
RUN poetry install --no-root --only main --no-interaction --no-ansi


FROM base AS qa-deps
# Install runtime + development dependencies
RUN poetry install --no-root --with dev --no-interaction --no-ansi
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*
ARG GITLEAKS_VERSION=8.24.2
RUN curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" -o /tmp/gitleaks.tar.gz && tar -xzf /tmp/gitleaks.tar.gz -C /tmp && mv /tmp/gitleaks /usr/local/bin/gitleaks && chmod +x /usr/local/bin/gitleaks && rm -f /tmp/gitleaks.tar.gz


FROM runtime-deps AS runtime

COPY ./src ./src
COPY ./docker/app/entrypoint.sh /app/docker/app/entrypoint.sh

ENV PYTHONPATH=/app/src

RUN chmod +x /app/docker/app/entrypoint.sh
RUN python /app/src/manage.py collectstatic --noinput


FROM qa-deps AS qa

COPY ./src ./src
COPY ./docker/app/entrypoint.sh /app/docker/app/entrypoint.sh

ENV PYTHONPATH=/app/src

RUN chmod +x /app/docker/app/entrypoint.sh
RUN python /app/src/manage.py collectstatic --noinput
