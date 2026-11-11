# Getting started

This guide runs the governed native ETH demonstration on local Anvil. Commands
start at the repository root unless a block explicitly changes directory.

## Install prerequisites

Use Linux, Python 3.12 or newer, Node.js 24, npm, Docker Engine with Compose v2,
GNU Make, Git and curl. Python packages require a virtual environment. The
[installer](../scripts/install_dev.sh) installs backend/IoT development dependencies,
Foundry npm binaries at 1.7.1, Solidity 0.8.24 with checksum verification,
OpenZeppelin v5.4.0, forge-std v1.9.7 and frontend dependencies.

```bash
./scripts/install_dev.sh
source .venv/bin/activate
```

`DEV_VENV` and `DEV_TOOLS` can select other installation directories. If selecting
a different tools directory, also pass it to Make, for example
`make DEV_TOOLS=/absolute/tools contracts-build`. The Docker node uses Foundry
v1.5.0 independently of host tools. Keep network proxy and certificate trust
configured in managed environments; see [deployment](deployment.md).

## Start infrastructure, migrations and applications

```bash
make setup
make contracts-build
make demo
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8080/api/v1/openapi.json >/dev/null
make ps
```

`make setup` generates missing local JWT/oracle/seed credentials in the ignored,
mode-0600 `infrastructure/docker/.env`, builds images and waits for dependencies.
The `migrate` service applies `alembic upgrade head` before API/subscriber/worker
startup. No revision generation or schema creation occurs in application startup.
The setup command itself does not deploy contracts, seed users or start a simulator.

`make demo` separately commissions a deterministic SQLModel community, five
participant users/homes, fifteen simulated devices and a separate governance
fixture. It deploys timelock, registry, SUN, settlement and vault contracts, then
uses actual governance transactions to approve policy, membership, nodes and
meters. The backend oracle has distinct local keys and limited authority.
Rerunning checks identity/deployment/credentials and preserves existing balances,
passwords, revocations and unrelated records; conflicts stop for review.

## Open the application and connect a local wallet

Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)**. Log in with `govdemo1@solar.local` (producer/operator)
or `govdemo2@solar.local` (consumer); `govadmin@solar.local` is the local governance
fixture. Read `SEED_PASSWORD` privately from the environment file, without posting
or committing it. The [configuration guide](configuration.md) explains every
runtime configuration surface.

The bootstrap exports encrypted development keystores under `.run/demo/wallets`,
using `SEED_PASSWORD`. Import the required keystore securely into an isolated
local-development wallet if manually signing. Add a local wallet network with
RPC `http://127.0.0.1:8545`, chain ID `31337`, and symbol `ETH`. These fixtures are
funded/unlocked only on guarded local Anvil; never reuse their keys publicly.

Application login and wallet connection are separate. Connecting does not prove
ownership: ordinary accounts must sign the API wallet challenge and obtain approved
community membership. The demonstrator provisions its own local fixtures explicitly.

## Execute the finite demonstration

```bash
make demo-scenario
```

This publishes authenticated, explicitly simulated MQTT boundary readings, verifies
invalid credentials and deduplication, then uses the running worker, API and real
Anvil receipts. Producer home 1 exports 5 kWh; consumer home 2 has 3 kWh eligible
demand. At 0.001 test ETH/kWh, 3 kWh settles for 0.003 ETH, 2 kWh remains unallocated,
3 SUN is delivered and retired, and the producer withdraws 0.003 ETH. The consumer's
0.01 ETH deposit leaves 0.007 ETH available.

The local timelock fixture finalizes the reviewed batch; this automatic local
procedure refuses Sepolia. `.run/demo/scenario.json` journals participant hashes
before confirmation. A completed rerun verifies the existing result without
another payment or retirement. Public local evidence is retained in
[verification](verification.md); current private runtime output is
`.run/demo/scenario-report.json`.

## Start continuous simulation

```bash
make simulate
```

The optional overlay runs REALTIME v2 MQTT against registered homes 3, 4 and 5,
using generated `.run/demo/compose.env`, registry, catalogue and private credential
bindings. Homes 1/2 remain reserved for the finite scenario. Never mix independent
counter/sequence streams on one meter. Interval accounting waits for observed
boundaries and the two-minute grace period; it is not an instant minting loop.
See [IoT](iot.md) for offline/fault modes and physical commissioning.

## Frontend development

For hot reload alongside the running Docker API:

```bash
cd apps/frontend
npm run dev -- --host 127.0.0.1
```

Open **[http://127.0.0.1:5173](http://127.0.0.1:5173)**. Bootstrap writes public chain/registry/timelock values
to `.env.local`; Vite proxies `/api` to the loopback API. Frontend variables are
public build inputs. Never copy backend secrets or authenticated RPC credentials
into them. [Development](development.md) covers browser fixtures and tests.

## Plain SQLModel seeds

`make seed` is a separate ungoverned fixture path, not a substitute for `make demo`.
The [seed entry point](../scripts/seed_db.sh) requires an explicit `DATABASE_URL`,
`JWT_SECRET` and development `SEED_PASSWORD` in the calling environment. Because the
prototype does not publish PostgreSQL to the host, use an intentionally reachable
development database or run the module inside its configured API container.

[The seed](../apps/backend/src/seed.py) constructs canonical models under a database
advisory lock: five homes, fifteen devices and unverified wallet placeholders.
Optional `SEED_DEVICE_KEY` authorizes new demo meter records and exports a registry
plus private bindings under `SEED_OUTPUT_DIR`; it does not authorize governed chain
state. Existing passwords/statuses/revocations and private output files are
preserved. No telemetry, credits, tokens or paid history is fabricated.

## Stop and resume

```bash
make down
make up
```

These preserve persistent volumes. Preserve PostgreSQL and Anvil history together;
contract addresses and financial projections cannot safely survive an independent
chain reset. Destructive cleanup is intentionally outside normal startup.
Operational failures and Sepolia configuration belong in [deployment](deployment.md).
