#!/usr/bin/env bash
# =============================================================================
# Load every SQL seed under database/seeds/ into the running Postgres.
#
# Idempotent: every seed uses INSERT ... ON CONFLICT DO NOTHING, so
# running this twice is safe.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infrastructure/docker/docker-compose.yml"
DB_USER="${POSTGRES_USER:-solar}"
DB_NAME="${POSTGRES_DB:-solar}"

log() { printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()  { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }

if ! docker compose -f "${COMPOSE_FILE}" ps timescaledb --format json \
     | grep -q '"Health":"healthy"'; then
  printf "\033[1;33m! timescaledb is not healthy yet; waiting...\033[0m\n"
  for _ in {1..30}; do
    if docker compose -f "${COMPOSE_FILE}" ps timescaledb --format json \
         | grep -q '"Health":"healthy"'; then
      break
    fi
    sleep 2
  done
fi

for seed in "${ROOT_DIR}"/database/seeds/*.sql; do
  [[ -f "${seed}" ]] || continue
  log "Loading $(basename "${seed}")"
  docker compose -f "${COMPOSE_FILE}" exec -T timescaledb \
    psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -q < "${seed}"
done

ok "Seeds loaded"