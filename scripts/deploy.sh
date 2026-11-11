#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/apps/backend${PYTHONPATH:+:$PYTHONPATH}"
exec python scripts/deploy_native.py "$@"
