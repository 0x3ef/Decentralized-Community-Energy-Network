#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infrastructure/docker/compose.tests.yml"
TEST_COMPOSE=(docker compose --project-name solar-prototype-tests -f "$COMPOSE_FILE")
"${TEST_COMPOSE[@]}" up -d --wait --wait-timeout 60
TEST_DATABASE_NAME="solar_test_$(python -c 'import uuid; print(uuid.uuid4().hex[:16])')"
"${TEST_COMPOSE[@]}" exec -T postgres createdb -U solar "$TEST_DATABASE_NAME"
trap '"${TEST_COMPOSE[@]}" exec -T postgres dropdb -U solar --if-exists "$TEST_DATABASE_NAME"' EXIT
export DATABASE_URL="postgresql+asyncpg://solar:solar@localhost:55432/$TEST_DATABASE_NAME"
export WEB3_PROVIDER_URL=http://localhost:18545
export MQTT_HOST=localhost MQTT_PORT=18884 REDIS_URL=redis://localhost:16379/0
# Fresh, ephemeral test-only signing secret; never print it.
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
cd "$ROOT_DIR/apps/backend"
alembic upgrade head
python -m pytest "$@"
