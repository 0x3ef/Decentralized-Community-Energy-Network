#!/usr/bin/env bash
# Canonical entry point; backend tests include the real MQTT/Anvil integrations.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
case "${1:-all}" in
  --contracts) exec make test-contracts ;;
  --backend) shift; exec ./scripts/test_backend.sh "$@" ;;
  --iot) shift; exec ./scripts/test_iot.sh "$@" ;;
  --frontend) exec make test-frontend ;;
  --browser) exec make test-browser ;;
  --integration|all) exec make test ;;
  *) printf '%s\n' 'Usage: scripts/test.sh [all|--contracts|--backend|--iot|--frontend|--integration|--browser]' >&2; exit 2 ;;
esac
