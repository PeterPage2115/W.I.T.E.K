# WITEK — Dockerfile (produkcja)
# Multi-stage build — mniejszy obraz (bez gcc i nagłówków dev)

# ── Stage 1: Budowanie zależności ──────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Obraz runtime ────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Tylko biblioteki runtime (libpq5), curl do healthchecka, postgresql-client do pg_isready
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl postgresql-client && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
# For web-only mode (no bot/scheduler): gunicorn wsgi:app -b 0.0.0.0:5000 -w 2
CMD ["python", "run.py", "--scheduled", "--port", "5000"]
