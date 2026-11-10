#!/usr/bin/env bash
# =============================================================================
# Bootstrap the Solar Energy Market local environment.
#
# This script:
#   1. Verifies prerequisites (docker, docker compose v2, python3, forge, jq).
#   2. Creates infrastructure/docker/.env from the example if missing.
#   3. Compiles the Solidity contracts (produces contracts/out).
#   4. Generates the gRPC stubs inside iot/.
#   5. Builds every Docker image.
#   6. Starts the full stack and waits for health.
#   7. Deploys the contracts to Anvil.
#   8. Injects the deployed addresses into the .env file.
#   9. Restarts the backend so it picks up the addresses.
#  10. Loads the SQL seeds.
#
# Usage:
#   ./scripts/setup.sh            # incremental
#   ./scripts/setup.sh --clean    # wipe volumes and artifacts first
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infrastructure/docker/docker-compose.yml"
ENV_FILE="${ROOT_DIR}/infrastructure/docker/.env"
ENV_EXAMPLE="${ROOT_DIR}/infrastructure/docker/.env.example"
ANVIL_RPC="http://127.0.0.1:8545"
DEPLOY_JSON="${ROOT_DIR}/contracts/deployments/31337.json"

# -----------------------------------------------------------------------------
# Pretty printing
# -----------------------------------------------------------------------------
log() { printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()  { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m! %s\033[0m\n" "$*"; }
err() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; }

# -----------------------------------------------------------------------------
# 1. Prerequisites
# -----------------------------------------------------------------------------
log "Checking prerequisites"
for cmd in docker python3 jq forge; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    err "Missing required command: ${cmd}"
    case "${cmd}" in
      forge) err "Install Foundry: curl -L https://foundry.paradigm.xyz | bash && foundryup" ;;
      jq)    err "Install jq: apt-get install jq" ;;
    esac
    exit 1
  fi
done
docker compose version >/dev/null 2>&1 || {
  err "docker compose v2 is required"
  exit 1
}
ok "Prerequisites satisfied"

# -----------------------------------------------------------------------------
# 2. Environment file
# -----------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  log "Creating ${ENV_FILE} from example"
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  ok "Environment file created"
fi

# The deployment script and the backend must use the same Anvil account.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
export PRIVATE_KEY="${PRIVATE_KEY:-${BACKEND_PRIVATE_KEY:-}}"
export BACKEND_PRIVATE_KEY="${BACKEND_PRIVATE_KEY:-${PRIVATE_KEY}}"
if [[ "${PRIVATE_KEY}" == *'${'* || "${PRIVATE_KEY}" != 0x* ]]; then
  export PRIVATE_KEY=""
fi
if [[ -z "${PRIVATE_KEY}" ]]; then
  # This is Anvil's documented account #0 key and is safe only for local
  # development. Production deployments must provide their own key.
  export PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
  export BACKEND_PRIVATE_KEY="${PRIVATE_KEY}"
  warn "Using Anvil account #0 for local development"
fi

# -----------------------------------------------------------------------------
# 3. Optional clean
# -----------------------------------------------------------------------------
if [[ "${1:-}" == "--clean" ]]; then
  log "Stopping stack and removing volumes"
  docker compose -f "${COMPOSE_FILE}" down -v
  rm -rf "${ROOT_DIR}/contracts/out" "${ROOT_DIR}/contracts/cache"
  rm -f "${DEPLOY_JSON}"
  ok "Clean complete"
fi

# -----------------------------------------------------------------------------
# 4. Compile contracts (must run before docker build)
# -----------------------------------------------------------------------------
log "Compiling contracts"
(cd "${ROOT_DIR}/contracts" && forge build >/dev/null)
ok "Contracts compiled"

# -----------------------------------------------------------------------------
# 5. Generate gRPC stubs
# -----------------------------------------------------------------------------
log "Generating gRPC stubs"
(cd "${ROOT_DIR}/iot" && make protos >/dev/null)
ok "gRPC stubs ready"

# -----------------------------------------------------------------------------
# 6. Build images
# -----------------------------------------------------------------------------
log "Building images"
docker compose -f "${COMPOSE_FILE}" build
ok "Images built"

# -----------------------------------------------------------------------------
# 7. Start stack
# -----------------------------------------------------------------------------
log "Starting stack"
docker compose -f "${COMPOSE_FILE}" up -d

log "Waiting for services to become healthy"
for i in {1..60}; do
  unhealthy=$(docker compose -f "${COMPOSE_FILE}" ps --format json \
    | jq -s '[.[] | select(.State == "running" and .Health != null and .Health != "healthy")] | length')
  if [[ "${unhealthy}" -eq 0 ]]; then
    ok "All services healthy"
    break
  fi
  if [[ "${i}" -eq 60 ]]; then
    err "Timeout waiting for services; run 'docker compose ps' to inspect"
    exit 1
  fi
  sleep 2
done

# -----------------------------------------------------------------------------
# 8. Deploy contracts to Anvil
# -----------------------------------------------------------------------------
log "Deploying contracts to Anvil"
(
  cd "${ROOT_DIR}/contracts"
  forge script script/Deploy.s.sol \
    --rpc-url "${ANVIL_RPC}" \
    --broadcast \
    --silent
)
if [[ ! -f "${DEPLOY_JSON}" ]]; then
  err "Deployment file not found at ${DEPLOY_JSON}"
  exit 1
fi
ok "Contracts deployed"

# -----------------------------------------------------------------------------
# 9. Inject addresses into .env
# -----------------------------------------------------------------------------
SUN=$(jq -r '.SUNToken' "${DEPLOY_JSON}")
MKT=$(jq -r '.EnergyMarketplace' "${DEPLOY_JSON}")
RED=$(jq -r '.RedemptionManager' "${DEPLOY_JSON}")

log "Injecting contract addresses into ${ENV_FILE}"
sed -i.bak \
  -e "s|^SUN_TOKEN_ADDRESS=.*|SUN_TOKEN_ADDRESS=${SUN}|" \
  -e "s|^ENERGY_MARKET_ADDRESS=.*|ENERGY_MARKET_ADDRESS=${MKT}|" \
  -e "s|^REDEMPTION_MANAGER_ADDRESS=.*|REDEMPTION_MANAGER_ADDRESS=${RED}|" \
  "${ENV_FILE}"
rm -f "${ENV_FILE}.bak"
ok "Addresses written"
printf "    SUN_TOKEN_ADDRESS=%s\n" "${SUN}"
printf "    ENERGY_MARKET_ADDRESS=%s\n" "${MKT}"
printf "    REDEMPTION_MANAGER_ADDRESS=%s\n" "${RED}"

# -----------------------------------------------------------------------------
# 10. Restart backend with new env
# -----------------------------------------------------------------------------
log "Restarting backend with new contract addresses"
docker compose -f "${COMPOSE_FILE}" up -d --force-recreate api subscriber
ok "Backend restarted"

# -----------------------------------------------------------------------------
# 11. Seed the database
# -----------------------------------------------------------------------------
log "Seeding database"
"${ROOT_DIR}/scripts/seed_db.sh"

ok "Setup complete"
printf "\n"
printf "  API:        http://localhost:8000/api/v1\n"
printf "  Health:     http://localhost:8000/health\n"
printf "  MQTT:       localhost:1883\n"
printf "  Anvil RPC:  %s\n" "${ANVIL_RPC}"
printf "  Postgres:   localhost:5432\n"
printf "\n"
printf "  Logs:       make logs\n"
printf "  Stop:       make down\n"
printf "\n"