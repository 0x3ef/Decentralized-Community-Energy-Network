#!/bin/sh

set -e

# Command substitution keeps the URL out of startup logs. SQLAlchemy preserves
# percent-encoded passwords and query options while changing only host/port.
if [ -n "${DATABASE_HOST_OVERRIDE:-}" ]; then
    DATABASE_URL="$(python -m src.core.docker_database)"
    export DATABASE_URL
fi

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
