#!/bin/sh

set -e

echo "============================================"
echo " SOLAR ENERGY MARKET - BACKEND STARTUP"
echo "============================================"

echo "Starting service: ${SERVICE_TYPE:-unknown}"

if [ -z "${JWT_SECRET:-}" ] ||
    [ "${JWT_SECRET}" = "local-development-jwt-secret-change-me-32-chars" ]; then
    echo "ERROR: JWT_SECRET must be provided; refusing to start with an implicit default." >&2
    exit 1
fi

if [ -z "${DATABASE_URL:-}" ] && [ -n "${POSTGRES_USER:-}" ] &&
    [ -n "${POSTGRES_PASSWORD:-}" ] && [ -n "${POSTGRES_DB:-}" ]; then
    export DATABASE_URL="$(
        python -c 'import os; from urllib.parse import quote; print("postgresql+asyncpg://{}:{}@{}:{}/{}".format(quote(os.environ["POSTGRES_USER"], safe=""), quote(os.environ["POSTGRES_PASSWORD"], safe=""), os.environ.get("POSTGRES_HOST", "timescaledb"), os.environ.get("POSTGRES_PORT", "5432"), quote(os.environ["POSTGRES_DB"], safe="")))'
    )"
fi

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "Running database migrations..."

    alembic upgrade head

    echo "Database migrations completed successfully."
fi

echo "Starting application..."

exec "$@"