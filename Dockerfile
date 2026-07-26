# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYFIX_DB_PATH=/app/data/playfix.sqlite3

WORKDIR /app

# Install dependencies first (better layer caching), then the package.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as an unprivileged user; persist the SQLite DB under /app/data.
RUN useradd --create-home --uid 10001 playfix \
    && mkdir -p /app/data \
    && chown -R playfix:playfix /app
USER playfix

VOLUME ["/app/data"]

CMD ["python", "-m", "playfix"]
