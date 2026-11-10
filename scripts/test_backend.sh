#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infrastructure/docker/compose.tests.yml"
docker compose -f "$COMPOSE_FILE" up -d --wait --wait-timeout 60
export DATABASE_URL=postgresql+asyncpg://solar:solar@localhost:55432/solar_tests
export WEB3_PROVIDER_URL=http://localhost:18545
export MQTT_HOST=localhost MQTT_PORT=18884 REDIS_URL=redis://localhost:16379/0
# Fresh, ephemeral test-only signing secret; never print it.
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
cd "$ROOT_DIR/apps/backend"
alembic upgrade head
python -m pytest "$@"
