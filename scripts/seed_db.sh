#!/usr/bin/env bash
# Use existing configured DATABASE_URL; reviewed migrations must run first.
set -euo pipefail
: "${DATABASE_URL:?Set DATABASE_URL explicitly to the development database}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$ROOT_DIR/apps/backend${PYTHONPATH:+:$PYTHONPATH}" python -m src.seed
