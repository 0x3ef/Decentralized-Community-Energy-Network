#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [ ! -f infrastructure/docker/.env ]; then
  python scripts/init_local_env.py
fi
docker compose -f infrastructure/docker/compose.prototype.yml up -d --build
printf '%s\n' 'Stack started. Create a community through the API, deploy its contracts with scripts/deploy.sh COMMUNITY_UUID, then register the public deployment.'
