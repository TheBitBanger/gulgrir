FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==2.0.0"

WORKDIR /app
# Only copy these files for better layer caching, when only the application code changes
COPY pyproject.toml poetry.lock ./

# Install python dependencies
RUN poetry config virtualenvs.create false
RUN poetry install --no-root --only main --no-interaction --no-ansi

COPY ./src ./src
COPY ./docker/scripts/entrypoint.sh /app/docker/scripts/entrypoint.sh

ENV PYTHONPATH=/app/src

RUN chmod +x /app/docker/scripts/entrypoint.sh
