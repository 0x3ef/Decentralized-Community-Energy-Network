#!/bin/sh

set -e

echo "============================================"
echo " SOLAR ENERGY MARKET - BACKEND STARTUP"
echo "============================================"

echo "Starting service: ${SERVICE_TYPE:-unknown}"

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "Running database migrations..."

    alembic upgrade head

    echo "Database migrations completed successfully."
fi

echo "Starting application..."

exec "$@"