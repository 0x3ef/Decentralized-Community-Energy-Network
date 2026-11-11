# Configuration

Sources of truth are the [backend settings](../apps/backend/src/core/config.py),
[IoT settings](../iot/config/settings.py),
[frontend example](../apps/frontend/.env.example), deployment scripts and
[prototype Compose](../infrastructure/docker/compose.prototype.yml). Names below
are implemented settings, not a promise that every component reads every file.

## Files, precedence and secrets

| File or surface | Reader and purpose |
| --- | --- |
| [.env.example](../.env.example) | Template used by `scripts/init_local_env.py` |
| [infrastructure/docker/.env.example](../infrastructure/docker/.env.example) | Matching local template for direct Compose users |
| `infrastructure/docker/.env` | Ignored local runtime configuration; generated without printing secrets |
| [infrastructure/docker/.env.sepolia.example](../infrastructure/docker/.env.sepolia.example) | Explicit public-testnet template; copy to ignored `.env.sepolia` |
| Backend process environment or working-directory `.env` | Pydantic Settings; process environment takes precedence |
| [iot/.env.example](../iot/.env.example) | Standalone simulator/gateway template; environment overrides `.env`; empty settings are ignored |
| `apps/frontend/.env.local` | Vite public development/build inputs; bootstrap writes confirmed local fallbacks |
| `.run/demo/simulator.env`, `.run/demo/compose.env` | Private meter credential bindings and host paths for simulation overlay |

Compose's `--env-file` supplies interpolation. The prototype backend also explicitly
loads its `.env` service file; inline `environment` values take precedence. It fixes
container database/Redis/RPC/MQTT hostnames, so changing host-oriented defaults in
`.env` alone does not change those routes. The Sepolia overlay replaces RPC/chain
settings. It still inherits the local backend env-file surface: isolate the public
runtime, configure its service environment deliberately, and check effective values
without printing secrets. The overlay does not provision a hardened public broker
or change the prototype's fixed local database credentials.

JWT secrets, signing keys, device credentials, wallet keystores, bearer tokens and
authenticated RPC URLs are private. Keep ignored files access-controlled; every
`VITE_*` value is public. Pydantic configuration errors hide input values, but
arbitrary shell commands, Compose config output and third-party logs can still
expose environment data. See [security](../SECURITY.md).

## Backend and authentication

Defaults here are Python settings defaults unless explicitly marked as Compose.
An empty default means the capability is unconfigured.

| Variable | Default / format | Requirement and purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development`, string | Local bootstrap requires development; production rejects local chain IDs |
| `DATABASE_URL` | `postgresql+asyncpg://solar:solar@localhost:5432/solar` | Async PostgreSQL DSN; Compose overrides host to `timescaledb` and uses local fixture credentials |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URI; Compose uses `redis`; revocation, heartbeats and optional mail broker |
| `JWT_SECRET` | No default; 32+ characters | Required in every backend process, including migrations |
| `JWT_ALGORITHM` | `HS256` | JWT signing/verification algorithm |
| `CORS_ORIGINS` | JSON array of localhost/127.0.0.1 origins on 5173 and 8080 | Explicit allowed browser origins, not a comma-separated string |
| `LOG_LEVEL` | `INFO` | Python logging level |

The local generator creates JWT/oracle/seed values only for local configuration and
preserves existing runtime settings. It does not repair an existing empty JWT or
oracle key automatically; resolve invalid existing settings deliberately.

### Optional mail

Signup/login do not require mail delivery. Password reset queues Celery mail work,
but the canonical Compose stack does not start a mail worker. These defaults do not
establish a verified password-reset deployment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | Empty | SMTP credentials, private |
| `MAIL_FROM` | `noreply@example.com` | Sender placeholder, not a project contact |
| `MAIL_FROM_NAME` | `Solar Energy Market` | Sender display name |
| `MAIL_SERVER`, `MAIL_PORT` | `localhost`, `587` | SMTP host/port |
| `MAIL_STARTTLS`, `MAIL_SSL_TLS` | `true`, `false` | Transport TLS controls |
| `USE_CREDENTIALS`, `VALIDATE_CERTS` | `true`, `true` | Mail authentication and certificate validation |
| `DOMAIN` | `localhost:8000` | Host used when constructing reset links |

## Blockchain and workers

| Variable | Default / format | Requirement and purpose |
| --- | --- | --- |
| `WEB3_PROVIDER_URL` | `http://localhost:8545` | Backend RPC; Compose uses `http://anvil:8545`; authenticated URLs are private |
| `CHAIN_ID` | `31337`, integer | Must match RPC; governed tooling allows 31337/1337 or Sepolia 11155111 |
| `COMMUNITY_REGISTRY_ADDRESS` | Empty, EVM address | Governed registry; bootstrap updates local configuration |
| `GOVERNANCE_TIMELOCK_ADDRESS` | Empty, EVM address | Authorized timelock for governance preparation |
| `BACKEND_PRIVATE_KEY` | Empty, 32-byte hex key | Dedicated oracle/settlement signer; required for worker transactions, never a participant key |
| `BLOCKCHAIN_CONFIRMATION_BLOCKS` | `2`, integer | Backend receipt/index depth; public overlay requires 3 |
| `BLOCKCHAIN_RECEIPT_TIMEOUT_SECONDS` | `120` | Receipt wait bound |
| `NATIVE_SETTLEMENT_ENABLED` | `true` | Native stage in community worker |
| `LEGACY_SETTLEMENT_ENABLED` | `false` | Explicit historical ERC-20 stage; not required for native demo |
| `NATIVE_SETTLEMENT_START_BLOCK` | `0`, nonnegative integer | Initial native scan bound; use earliest deployment block publicly |
| `NATIVE_SETTLEMENT_LOOKBACK_HOURS` | `24`, range 1–168 | Automatic discovery horizon; explicit calculation can backfill |
| `NATIVE_SETTLEMENT_INTERVAL_LIMIT` | `200`, range 1–2000 | Bounded per-community interval discovery |
| `SUN_TOKEN_ADDRESS`, `MOCK_USD_ADDRESS`, `ENERGY_MARKET_ADDRESS`, `COMPENSATION_ADDRESS`, `REDUCTION_MANAGER_ADDRESS` | Empty | Historical/global integration settings; native governed addresses come from per-community deployment records; preserve the implemented `REDUCTION` spelling |

There is no environment-controlled automatic governance finalization. The worker
runs approximately every two seconds; interval/grace policy is implemented in the
energy code, not a documented `WORKER_INTERVAL` setting.

### Deployment-script inputs

| Variable | Default / format | Reader and purpose |
| --- | --- | --- |
| `SEPOLIA_RPC_URL`, `SEPOLIA_DEPLOYER_PRIVATE_KEY` | No usable default | Python Sepolia deployer; required even for preflight |
| `GOVERNANCE_PROPOSER_ADDRESS`, `GOVERNANCE_EXECUTOR_ADDRESS`, `ORACLE_ADDRESS` | No default; nonzero EVM addresses | Python deployer requires explicit authorities; oracle must differ from deployer/proposer/executor |
| `DEPLOYER_PRIVATE_KEY` | No default | Python local deployer / alternative Foundry governed script |
| `COMMUNITY_ID` | No default; nonzero bytes32 | Alternative Foundry `DeployGoverned.s.sol`; Python CLI takes a UUID argument instead |
| `GOVERNANCE_DELAY` | Local 0 / Sepolia 86400 seconds | Alternative Foundry script only; Sepolia cannot go below one day |
| `CHALLENGE_PERIOD` | `86400` seconds | Alternative Foundry script only; positive uint64, public minimum one day |

Canonical Python deployment fixes public timelock/challenge to one day and requires
three confirmations; its local challenge is one second. These script inputs are
not backend Settings fields. No explorer verification credentials are integrated
into the canonical Python deployment command.

## MQTT ingestion

| Variable | Backend default / format | Purpose |
| --- | --- | --- |
| `MQTT_HOST`, `MQTT_PORT` | `localhost`, `1883` | Broker; Compose overrides host to `mosquitto` |
| `MQTT_TOPIC` | `solar/#` | Subscription filter; binding checks still enforce exact device identity |
| `MQTT_QOS`, `MQTT_CLIENT_ID` | `1`, `solar-subscriber` | Delivery quality and stable persistent client identity |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Unset | Private broker login; independent of payload credential |
| `MQTT_TLS_CA`, `MQTT_TLS_CERT`, `MQTT_TLS_KEY` | Unset; readable paths | Trusted CA, optional client certificate/key |
| `QUEUE_MAXSIZE`, `BATCH_SIZE` | `10000`, `200` | Ingest queue and database batch bounds |
| `BATCH_FLUSH_SECONDS` | `1`, number | Partial-batch flush interval |
| `MAX_METER_POWER_W` | `100000` | Plausibility ceiling for counter deltas; not proof of calibrated rating |
| `MAX_TELEMETRY_BYTES` | `65536` | MQTT body limit in bytes |

## Simulator and gateway

IoT settings are case-insensitive environment names; uppercase names are used here.
Unless otherwise stated, each is optional and its default is shown.

| Variable | Default / format | Purpose |
| --- | --- | --- |
| `INTERVAL_SECONDS` | `15`, positive number | Sampling cycle, not settlement interval |
| `RANDOM_SEED`, `SEQUENCE_OFFSET` | Unset; integers | Reproducible per-home RNG; CLI uses epoch offset if omitted |
| `DEVICE_REGISTRY` | Unset; JSON file path | Required for registered MQTT simulation; public UUIDs and credential environment names |
| `HOME_CATALOGUE_FILE` | Unset; JSON file path | Optional explicit home/sensor catalogue |
| `HOME_PROFILES_JSON` | `{}`, JSON object | Per-home profile overrides |
| `CHECKPOINT_PATH` | Unset; file path | Private persistent physical/sequencing/pending-delivery checkpoint |
| `USE_GRPC` | `false` | Direct v2 path by default; true selects diagnostic v1 gateway |
| `SIMULATION_MODE` | `REALTIME` | REALTIME, ACCELERATED or DETERMINISTIC |
| `SIMULATION_SPEED` | `1`, positive finite number | Offline acceleration; realtime requires normal clock |
| `SIMULATION_START` | Unset; aware ISO timestamp | Explicit offline clock start |
| `MAX_CYCLES` | Unset; positive integer | Bound CLI cycles; unset runs continuously |
| `FAULT_SCENARIO`, `FAULT_DEVICE` | `none`, unset | Explicit offline fault injection and optional sensor selector |
| `PUBLISHER` | `mqtt` | MQTT or console output |
| `GATEWAY_ADDRESS` | `gateway:50051` | Diagnostic gRPC destination |
| `GRPC_PORT`, `GRPC_MAX_WORKERS` | `50051`, `8` | Gateway listener and thread pool |
| `MQTT_HOST`, `MQTT_PORT` | `mosquitto`, `1883` | Simulator/gateway broker destination |
| `MQTT_CLIENT_ID`, `MQTT_QOS` | `solar-gateway`, `1` | Distinct stable identity; QoS range 0–2 |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Unset | Scoped broker credentials |
| `MQTT_TLS` | `false` | Enable certificate-verified TLS |
| `MQTT_CA_CERT`, `MQTT_CLIENT_CERT`, `MQTT_CLIENT_KEY` | Unset; readable paths | CA and optional mutual-TLS credentials |
| `LOG_LEVEL` | `INFO` | Simulator/gateway log level |

Registered device credential environment names are generated bindings in the
registry, not one fixed global credential setting. Never embed their values in
public JSON or checkpoint files.

## Local bootstrap and host tooling

| Variable | Default / format | Reader and purpose |
| --- | --- | --- |
| `SEED_PASSWORD` | Required; 12+ characters, at most 72 UTF-8 bytes for governed bootstrap | Development login and encrypted local keystores; generated by local setup |
| `SEED_DEVICE_KEY` | 32+ characters | Required for governed bootstrap; deterministic local wallet/device derivation; optional in plain seed |
| `SEED_OUTPUT_DIR` | `/tmp/solar-market-demo` | Plain seed's registry and credential output |
| `DEMO_OUTPUT_DIR`, `CONTRACT_ARTIFACT_DIR` | `/run/demo`, `/artifacts` | Bootstrap module paths inside one-off container; wrapper mounts actual host paths |
| `DEMO_API_URL`, `DEMO_RPC_URL` | `http://127.0.0.1:8000`, `http://127.0.0.1:8545` | Finite scenario HTTP/RPC endpoints |
| `DEMO_MQTT_HOST`, `DEMO_MQTT_PORT` | `127.0.0.1`, `1883` | Finite scenario broker |
| `DEV_VENV`, `DEV_TOOLS` | Repository `.venv`, `.dev-tools` | Dependency installer paths; Make also reads `DEV_TOOLS` |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | System Chromium if present, otherwise Playwright browser | Browser test executable override |

## Compose-only inputs

| Variable | Default / requirement | Purpose |
| --- | --- | --- |
| `CLOUD_CA_BUNDLE` | `/etc/ssl/certs/ca-certificates.crt` | Combined CA bundle for BuildKit and runtime trust mounts |
| `SIMULATOR_ENV_FILE`, `SIMULATOR_REGISTRY_FILE`, `SIMULATOR_CATALOGUE_FILE` | Required by simulation overlay | Host paths; `make demo` writes bindings in `.run/demo/compose.env` |
| `SIMULATOR_MQTT_CLIENT_ID` | `solar-simulator` | Unique simulator session identity; keep distinct from concurrent gateways and align its status-topic ACL |
| `SIMULATOR_MQTT_PORT`, `SIMULATOR_MQTT_TLS` | `1883`, `false` | Simulation overlay broker mode |
| `SIMULATOR_CA_FILE` | System CA bundle | Public CA mounted into simulator |
| `MQTT_PASSWORD_FILE`, `MQTT_ACL_FILE` | Required for authenticated overlays | Private broker files |
| `MQTT_TLS_DIRECTORY`, `MQTT_SUBSCRIBER_PASSWORD` | Required for TLS overlay | Broker certificate directory and subscriber credential |

Authenticated overlays also set subscriber identity/TLS environment explicitly.
The prototype hardcodes its local PostgreSQL credentials; `POSTGRES_PASSWORD` in
an unrelated legacy Compose file does not configure the canonical stack.
`NO_PROXY` and `no_proxy` include internal Docker names/loopback; inherited external
proxy variables and certificate verification stay enabled.

## Frontend public settings

| Variable | Fallback / format | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | `/api/v1` | Complete API prefix; Vite/nginx proxy this relative path |
| `VITE_CHAIN_ID` | `31337` | Default network; supported local IDs and Sepolia 11155111 |
| `VITE_ANVIL_RPC_URL` | `http://127.0.0.1:8545` | Local public RPC fallback |
| `VITE_SEPOLIA_RPC_URL` | Empty; wallet must already know Sepolia | Optional browser-safe RPC; no private credentials |
| `VITE_REGISTRY_ADDRESS`, `VITE_TIMELOCK_ADDRESS` | Empty | Governance fallbacks; selected community's registry takes precedence |

Vite loads these at development start/build time. Docker forwards selected public
build arguments; changing runtime `.env` cannot rewrite already-built JavaScript.
`VITE_API_BASE_URL` belongs to the obsolete Compose file and is not the active
frontend setting. Always rebuild after changing public deployment configuration.
