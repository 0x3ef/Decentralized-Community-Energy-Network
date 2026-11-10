#!/usr/bin/env bash
# =============================================================================
# Run tests for every module.
#
# Usage:
#   ./scripts/test.sh                 # unit tests only
#   ./scripts/test.sh --integration   # include integration tests
#   ./scripts/test.sh --contracts     # contracts only
#   ./scripts/test.sh --iot           # iot only
#   ./scripts/test.sh --backend       # backend only
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infrastructure/docker/docker-compose.yml"
MODE="${1:-all}"

log() { printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()  { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }

run_contracts() {
  log "Contracts (Foundry)"
  (cd "${ROOT_DIR}/contracts" && forge test -vv)
  ok "Contracts passed"
}

run_iot() {
  log "IoT (pytest on host)"
  (cd "${ROOT_DIR}/iot" && make test)
  ok "IoT passed"
}

run_backend() {
  local pytest_args=(-m "not integration")
  if [[ "${MODE}" == "--integration" ]]; then
    pytest_args=(-m integration)
    log "Backend (integration, inside Docker)"
  else
    log "Backend (unit, inside Docker)"
  fi
  docker compose -f "${COMPOSE_FILE}" run --rm tests "${pytest_args[@]}"
  ok "Backend passed"
}

case "${MODE}" in
  --contracts) run_contracts ;;
  --iot)       run_iot ;;
  --backend)   run_backend ;;
  --integration)
    run_contracts
    run_iot
    run_backend
    ;;
  all)
    run_contracts
    run_iot
    run_backend
    ;;
  *)
    echo "Usage: $0 [--contracts|--iot|--backend|--integration|all]" >&2
    exit 1
    ;;
esac

ok "All requested test suites passed"