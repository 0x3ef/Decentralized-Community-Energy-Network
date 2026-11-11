#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
python scripts/init_local_env.py
docker compose --env-file infrastructure/docker/.env -f infrastructure/docker/compose.prototype.yml up -d --build --wait --wait-timeout 180
printf '%s\n' 'Stack started. See docs/getting-started.md for governed community proposals and native ETH deployment.'
