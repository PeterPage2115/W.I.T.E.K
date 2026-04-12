#!/bin/sh
set -e

# ── Wait for PostgreSQL (skip for SQLite) ────────────────────────
if echo "$DATABASE_URL" | grep -qi "^postgres"; then
    echo "[entrypoint] Waiting for PostgreSQL …"

    # Extract host:port from DATABASE_URL
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_PORT=${DB_PORT:-5432}

    retries=30
    until pg_isready -h "$DB_HOST" -p "$DB_PORT" -q 2>/dev/null; do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            echo "[entrypoint] ERROR: PostgreSQL not ready after 30 attempts" >&2
            exit 1
        fi
        echo "[entrypoint] PostgreSQL not ready — retrying ($retries left) …"
        sleep 1
    done
    echo "[entrypoint] PostgreSQL is ready."
fi

# ── Hand off to CMD ──────────────────────────────────────────────
exec "$@"
