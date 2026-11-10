#!/usr/bin/env bash
# =============================================================================
# Deploy the full stack or only the contracts.
#
# Usage:
#   ./scripts/deploy.sh local        # Anvil + Docker Compose + contracts
#   ./scripts/deploy.sh contracts    # contracts only, to RPC_URL
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infrastructure/docker/docker-compose.yml"
ENV_FILE="${ROOT_DIR}/infrastructure/docker/.env"
TARGET="${1:-local}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
export PRIVATE_KEY="${PRIVATE_KEY:-${BACKEND_PRIVATE_KEY:-}}"
if [[ "${PRIVATE_KEY}" == *'${'* || "${PRIVATE_KEY}" != 0x* ]]; then
  export PRIVATE_KEY=""
fi
if [[ -z "${PRIVATE_KEY}" && (
  "${TARGET}" == "local" ||
  "${RPC_URL:-http://127.0.0.1:8545}" == "http://127.0.0.1:8545"
) ]]; then
  export PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
fi
if [[ -z "${PRIVATE_KEY}" ]]; then
  echo "PRIVATE_KEY or BACKEND_PRIVATE_KEY must be a 0x-prefixed key" >&2
  exit 1
fi

log() { printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()  { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }

deploy_contracts() {
  local rpc="${1:-http://127.0.0.1:8545}"
  log "Compiling contracts"
  (cd "${ROOT_DIR}/contracts" && forge build >/dev/null)

  log "Deploying contracts to ${rpc}"
  (cd "${ROOT_DIR}/contracts" && \
    forge script script/Deploy.s.sol \
      --rpc-url "${rpc}" \
      --broadcast)
  ok "Contracts deployed"
}

inject_addresses() {
  local deploy_json="${ROOT_DIR}/contracts/deployments/31337.json"
  [[ -f "${deploy_json}" ]] || { log "No deployment JSON found"; return; }

  local sun mkt red
  sun=$(jq -r '.SUNToken'           "${deploy_json}")
  mkt=$(jq -r '.EnergyMarketplace'  "${deploy_json}")
  red=$(jq -r '.RedemptionManager'  "${deploy_json}")

  sed -i.bak \
    -e "s|^SUN_TOKEN_ADDRESS=.*|SUN_TOKEN_ADDRESS=${sun}|" \
    -e "s|^ENERGY_MARKET_ADDRESS=.*|ENERGY_MARKET_ADDRESS=${mkt}|" \
    -e "s|^REDEMPTION_MANAGER_ADDRESS=.*|REDEMPTION_MANAGER_ADDRESS=${red}|" \
    "${ENV_FILE}"
  rm -f "${ENV_FILE}.bak"
  ok "Contract addresses written to ${ENV_FILE}"
}

case "${TARGET}" in
  contracts)
    deploy_contracts "${RPC_URL:-http://127.0.0.1:8545}"
    if [[ -f "${ENV_FILE}" ]]; then
      inject_addresses
      if docker compose -f "${COMPOSE_FILE}" ps api --format json 2>/dev/null | grep -q '"State":"running"'; then
        log "Restarting blockchain-aware backend services"
        docker compose -f "${COMPOSE_FILE}" up -d --force-recreate api subscriber worker
      fi
    fi
    ;;
  local)
    log "Starting Anvil only"
    docker compose -f "${COMPOSE_FILE}" up -d anvil
    sleep 3

    deploy_contracts "http://127.0.0.1:8545"
    inject_addresses

    log "Starting the full stack"
    docker compose -f "${COMPOSE_FILE}" up -d

    log "Restarting backend with new addresses"
    docker compose -f "${COMPOSE_FILE}" up -d --force-recreate api subscriber
    ok "Local deployment complete"
    ;;
  *)
    echo "Usage: $0 {local|contracts}" >&2
    exit 1
    ;;
esac