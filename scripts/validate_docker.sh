#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infrastructure/docker/compose.tests.yml"
CANONICAL_COMPOSE="$ROOT_DIR/infrastructure/docker/compose.prototype.yml"
CANONICAL_ENV="$ROOT_DIR/infrastructure/docker/.env.example"
PROJECT="solar-compose-smoke"
COMPOSE=(docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE")

"${COMPOSE[@]}" config --quiet
COMPOSE_ENV_FILE="$CANONICAL_ENV" POSTGRES_PASSWORD=compose-validation \
  docker compose --env-file "$CANONICAL_ENV" -f "$CANONICAL_COMPOSE" config --quiet
trap '"${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true' EXIT
"${COMPOSE[@]}" up -d --wait --wait-timeout 90
"${COMPOSE[@]}" exec -T postgres pg_isready -U solar -d solar_tests >/dev/null
"${COMPOSE[@]}" exec -T redis redis-cli ping | grep -qx PONG
"${COMPOSE[@]}" exec -T anvil cast chain-id --rpc-url http://127.0.0.1:8545 | grep -qx 31337

echo "Docker test services passed configuration and readiness checks."
