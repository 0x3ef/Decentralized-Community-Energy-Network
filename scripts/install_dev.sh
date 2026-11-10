#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV_TOOLS="${DEV_TOOLS:-$ROOT_DIR/.dev-tools}"
DEV_VENV="${DEV_VENV:-$ROOT_DIR/.venv}"
mkdir -p "$DEV_TOOLS"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$DEV_TOOLS/pip-cache}"
export npm_config_cache="${npm_config_cache:-$DEV_TOOLS/npm-cache}"
python3 -m venv "$DEV_VENV"
"$DEV_VENV/bin/python" -m pip install -r "$ROOT_DIR/apps/backend/requirements.lock"
"$DEV_VENV/bin/python" -m pip install -e "$ROOT_DIR/apps/backend[dev]" -e "$ROOT_DIR/iot[dev]"
npm --prefix "$DEV_TOOLS" install @foundry-rs/forge@1.7.1 @foundry-rs/anvil@1.7.1 @foundry-rs/cast@1.7.1
if [ ! -d "$ROOT_DIR/contracts/lib/openzeppelin-contracts" ]; then
  git clone --depth 1 --branch v5.4.0 https://github.com/OpenZeppelin/openzeppelin-contracts.git "$ROOT_DIR/contracts/lib/openzeppelin-contracts"
fi
if [ ! -d "$ROOT_DIR/contracts/lib/forge-std" ]; then
  git clone --depth 1 --branch v1.9.7 https://github.com/foundry-rs/forge-std.git "$ROOT_DIR/contracts/lib/forge-std"
fi
curl -fL https://github.com/ethereum/solidity/releases/download/v0.8.24/solc-static-linux -o "$DEV_TOOLS/solc-0.8.24"
curl -fsSL https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/list.json -o "$DEV_TOOLS/solc-list.json"
"$DEV_VENV/bin/python" - "$DEV_TOOLS" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); listing=json.loads((root/'solc-list.json').read_text())
expected=next(item['sha256'] for item in listing['builds'] if item['path']==listing['releases']['0.8.24'])
if '0x'+hashlib.sha256((root/'solc-0.8.24').read_bytes()).hexdigest()!=expected:
    raise SystemExit('Solidity compiler checksum mismatch')
PY
chmod +x "$DEV_TOOLS/solc-0.8.24"
"$DEV_TOOLS/node_modules/.bin/forge" test --root "$ROOT_DIR/contracts" --use "$DEV_TOOLS/solc-0.8.24"
cd "$ROOT_DIR/apps/frontend"
npm ci
npm run build
npm run lint
