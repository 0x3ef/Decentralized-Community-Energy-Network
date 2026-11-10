# Solar Energy Market

Community energy marketplace for a solar neighbourhood. IoT sensors
feed validated telemetry into PostgreSQL, the backend mints SUN
credits on an EVM chain, and the frontend lets households trade and
redeem them.

The project runs **entirely locally** with Docker Compose. Every runtime
dependency (broker, database, cache, EVM node, API, and workers) is a
local container.

## 1. Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + wagmi + MetaMask |
| Backend API | Python 3.12 + FastAPI |
| Database | PostgreSQL 16 + TimescaleDB |
| Ingest | Python 3.12 + paho-mqtt |
| IoT simulation | Python 3.12 + grpcio + Mosquitto |
| Blockchain | Solidity 0.8.24 + Foundry (Anvil) |

## 2. Repository layout

| Directory | Responsibility |
|---|---|
| `apps/frontend` | React dashboard, MetaMask integration |
| `apps/backend` | FastAPI API, MQTT ingest, services, repositories, blockchain |
| `contracts` | Foundry project: SUNToken, EnergyMarketplace, RedemptionManager |
| `iot` | Stateful simulator, gRPC gateway, MQTT publisher, telemetry schema |
| `database` | Idempotent demo seeds; schema is owned by SQLAlchemy/Alembic |
| `infrastructure` | Docker Compose, Dockerfiles, Mosquitto config |
| `docs` | Architecture, MQTT topics, OpenAPI spec, contract docs, diagrams |
| `scripts` | Setup, seed, test, deploy automation |

## 3. Prerequisites

- Docker Engine 24+ with Compose v2
- Python 3.12
- Foundry (`forge`, `cast`, `anvil`) — install with
  `curl -L https://foundry.paradigm.xyz | bash && foundryup`
- `make`
- `jq` (used by `setup.sh` to inject contract addresses)
- On Gentoo, `forge` lives in `~/.foundry/bin`. Add it to your
  `PATH`:
  ```bash
  export PATH="$HOME/.foundry/bin:$PATH"
  ```

## 4. Quick start

```bash
# 1. Install Foundry dependencies (once)
cd contracts
forge install foundry-rs/forge-std
forge install OpenZeppelin/openzeppelin-contracts
forge build
cd ..

# 2. Install Python tooling for iot/ (once)
cd iot
pip install -e ".[dev]"
cd ..

# 3. Bootstrap everything
make setup
```

`make setup` runs `scripts/setup.sh`, which:

1. Verifies prerequisites.
2. Creates `infrastructure/docker/.env` from the example.
3. Compiles the Solidity contracts (`forge build`).
4. Generates the gRPC stubs (`make protos` in `iot/`).
5. Builds every Docker image.
6. Starts the stack and waits for all services to be healthy.
7. Deploys the contracts to Anvil.
8. Injects the deployed addresses into `.env`.
9. Restarts the backend so it picks them up.
10. Loads the SQL seeds.

At the end you should see:

```
✓ Setup complete

  API:        http://localhost:8000/api/v1
  Health:     http://localhost:8000/health
  Frontend:   http://localhost:8080
  MQTT:       localhost:1883
  Anvil RPC:  http://127.0.0.1:8545
  Postgres:   localhost:5432

  Logs:       make logs
  Stop:       make down
```

## 5. Services and ports

| Service | Container | Port | Purpose |
|---|---|---|---|
| `mosquitto` | `solar-mosquitto` | 1883 | MQTT broker |
| `timescaledb` | `solar-timescaledb` | 5432 | PostgreSQL + Timescale |
| `anvil` | `solar-anvil` | 8545 | Local EVM chain |
| `gateway` | `solar-gateway` | 50051 | gRPC server |
| `simulator` | `solar-simulator` | — | Telemetry generator |
| `subscriber` | `solar-subscriber` | — | MQTT → PostgreSQL |
| `api` | `solar-api` | 8000 | FastAPI HTTP API |
| `frontend` | `solar-frontend` | 8080 | React/Vite web application |

## 6. Verifying the stack

```bash
# Container status
make ps

# Tail logs from every service
make logs

# Health checks
curl http://localhost:8000/health
curl http://localhost:8080/health
docker compose -f infrastructure/docker/docker-compose.yml \
  exec timescaledb pg_isready -U solar -d solar
docker compose -f infrastructure/docker/docker-compose.yml \
  exec anvil cast block-number --rpc-url http://127.0.0.1:8545

# Inspect live MQTT traffic
docker compose -f infrastructure/docker/docker-compose.yml \
  exec mosquitto mosquitto_sub -h 127.0.0.1 -t 'solar/#' -v

# Inspect persisted telemetry
docker compose -f infrastructure/docker/docker-compose.yml \
  exec timescaledb psql -U solar -d solar -c \
  "SELECT device_id, sensor_type, quality_status, COUNT(*)
   FROM telemetry_messages tm
   JOIN devices d ON d.id = tm.device_id
   GROUP BY 1, 2, 3;"
```

## 7. Daily commands

```bash
make up               # start the stack
make down             # stop the stack, keep volumes
make logs             # tail logs
make ps               # container status
make seed             # reload SQL seeds (idempotent)
make test             # run all test suites
make contracts-deploy # redeploy contracts and update .env
make clean            # stop the stack and remove volumes
```

## 8. Testing

The test suite is split by module:

```bash
# Everything (contracts + iot + backend)
make test

# Individual suites
make test-contracts   # Foundry
make test-iot         # iot/ pytest
make test-backend     # backend pytest (inside Docker)

# Integration tests (requires a live broker + DB)
./scripts/test.sh --integration
```

The backend tests run inside the `tests` container, so they share the
same Docker network and see `mosquitto`, `timescaledb` and `anvil`
exactly as production would.

## 9. Documentation

| Document | Content |
|---|---|
| `docs/ARCHITECTURE.md` | System diagram, data flow, and boundaries |
| `docs/IOT_TELEMETRY.md` | MQTT telemetry contract |
| `docs/API.md` | HTTP API overview |
| `docs/BLOCKCHAIN_INTEGRATION.md` | Contract roles, lifecycle, deployment, and reconciliation |
| `docs/DATABASE.md` | Migration ownership and database model |
| `docs/diagrams/database.mmd` | Mermaid database entity relationship diagram |
| `iot/README.md` | IoT simulation model, configuration, commands, and troubleshooting |

## 10. Environment variables

Every runtime setting is read from `infrastructure/docker/.env`. The
full list lives in `.env.example`. The most important ones:

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER` | `solar` | Database user |
| `POSTGRES_PASSWORD` | `solar` | Database password |
| `POSTGRES_DB` | `solar` | Database name |
| `INTERVAL_SECONDS` | `15` | Simulator cycle period |
| `PUBLISHER` | `mqtt` | Gateway publisher: `console` or `mqtt` |
| `WEB3_PROVIDER_URL` | `http://anvil:8545` | EVM RPC endpoint |
| `SUN_TOKEN_ADDRESS` | (injected) | SUN token contract |
| `ENERGY_MARKET_ADDRESS` | (injected) | Marketplace contract |
| `REDEMPTION_MANAGER_ADDRESS` | (injected) | Redemption contract |
| `BACKEND_PRIVATE_KEY` | Anvil account #0 | Backend signer |
| `JWT_SECRET` | (required) | JWT signing key, at least 32 characters |

## 11. Troubleshooting

### `forge: command not found`

`foundryup` installs binaries under `~/.foundry/bin`, which is not on
`PATH` by default on some systems. Run:

```bash
export PATH="$HOME/.foundry/bin:$PATH"
```

and add the same line to your shell profile.

### `COPY failed: contracts/out: file does not exist`

`contracts/out` is the Foundry build directory. It does not exist
until you run `forge build`. Run it once and retry:

```bash
cd contracts && forge build && cd ..
make setup
```

### `ModuleNotFoundError: No module named 'grpc_tools'`

`grpc_tools` is a dev dependency of `iot/`. Install it:

```bash
cd iot
pip install -e ".[dev]"
```

If you are on a system with PEP 668 enforcement (Gentoo, Debian
testing), create a virtualenv first:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### `solar-gateway is unhealthy`

Check the logs first:

```bash
docker compose -f infrastructure/docker/docker-compose.yml \
  logs solar-gateway --tail=100
```

Common causes:

- `ModuleNotFoundError: config.settings` — the Docker image was built
  without the `config` package. Verify that
  `iot/config/__init__.py` exists and that
  `[tool.setuptools.packages.find].include` in `iot/pyproject.toml`
  contains `config*`.
- `ModuleNotFoundError: sensor_pb2` — the `sed` patch of the generated
  `sensor_pb2_grpc.py` did not apply. Rebuild without cache:
  `docker compose ... build --no-cache gateway`.

### The subscriber logs `Unknown device`

The ingest worker refuses to auto-provision devices. Load the seeds:

```bash
make seed
```

or register the device through the API:

```bash
curl -X POST http://localhost:8000/api/v1/devices \
  -H 'Content-Type: application/json' \
  -d '{"home_id":"...","device_code":"SM-CALI-001-001","device_type":"smart_meter"}'
```

## 12. Roadmap

The following extensions are planned but not implemented:

- Real-time notifications (WebSocket or Server-Sent Events).
- Multi-tenant authentication with per-home permissions.
- On-chain order book (matching currently happens off-chain).
- Price oracle for the redemption rate.
- Grafana dashboards fed by TimescaleDB.