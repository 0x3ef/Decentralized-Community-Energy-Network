#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker compose --project-name solar-prototype-tests -f "$ROOT_DIR/infrastructure/docker/compose.tests.yml" up -d mqtt
cd "$ROOT_DIR/iot"
export MQTT_HOST="${MQTT_HOST:-127.0.0.1}" MQTT_PORT="${MQTT_PORT:-18884}" GRPC_PORT=50052 GATEWAY_ADDRESS=127.0.0.1:50052 PUBLISHER=mqtt
python -m gateway.main > "$ROOT_DIR/iot/test-gateway.log" 2>&1 &
TEST_GATEWAY_PID=$!
trap 'kill "$TEST_GATEWAY_PID" 2>/dev/null || true; wait "$TEST_GATEWAY_PID" 2>/dev/null || true' EXIT
python - <<'PY'
import grpc,os
channel=grpc.insecure_channel(os.environ['GATEWAY_ADDRESS'])
try: grpc.channel_ready_future(channel).result(timeout=10)
finally: channel.close()
PY
python -m pytest "$@"
