#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -ne 1 ]; then
  printf '%s\n' 'Usage: scripts/deploy.sh COMMUNITY_UUID' >&2
  exit 2
fi
cd "$ROOT_DIR"
PYTHONPATH="$ROOT_DIR/apps/backend${PYTHONPATH:+:$PYTHONPATH}" python scripts/deploy_community.py "$1"
