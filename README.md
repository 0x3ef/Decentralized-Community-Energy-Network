# Decentralized Community Energy Network

A prototype for community energy accounting and settlement in Colombia. Authorized
meters report eligible grid injection and consumption; the platform verifies
intervals, issues SUN energy credits, allocates community energy and demonstrates
settlement using native test ETH.

**1 SUN = 1 kWh of verified eligible energy.** Holding SUN does not automatically
compensate consumption: retirement also requires an approved, financially delivered
consumption claim. Test ETH has no real monetary value. Blockchain transactions do
not route electricity, change official utility bills or authorize commercial energy
exchange under Colombian law.

## How it works

1. Governance approves a community, policy, memberships, nodes and meters.
2. Authenticated telemetry is validated and converted into observed energy intervals.
3. The backend allocates eligible injection to eligible demand and commits evidence.
4. Governance finalizes the oracle's batch; proven injection can then issue SUN.
5. Consumers deposit test ETH and producers escrow SUN. Funded allocations deliver
   SUN and credit producer earnings atomically.
6. Consumers separately retire delivered SUN; producers withdraw their earnings.

DePIN (decentralized physical infrastructure networks) describes the metering and
node layer; current demonstrations use explicitly simulated devices. DeFi
(decentralized finance) describes wallet and contract settlement. Verification,
indexing and orchestration still depend on authorized backend services and
operators. See [architecture](docs/architecture.md) and [trust assumptions](SECURITY.md).

## Stack and repository

| Directory | Implemented responsibility |
| --- | --- |
| [apps/frontend](apps/frontend) | Spanish React 19 / TypeScript UI; Vite, TanStack Query, viem, Tailwind, Recharts |
| [apps/backend](apps/backend) | FastAPI, SQLModel/SQLAlchemy, Alembic, MQTT ingest and settlement workers |
| [iot](iot) | Coordinated Python simulation, v2 MQTT and diagnostic v1 gRPC gateway |
| [contracts](contracts) | Solidity 0.8.24, OpenZeppelin contracts, Foundry tests and deployment tooling |
| [infrastructure/docker](infrastructure/docker) | PostgreSQL 16/TimescaleDB, Redis, Mosquitto, Anvil, API, workers and nginx |
| [scripts](scripts) | Dependency installation, setup, bootstrap, tests and explicit deployment |
| [database](database) | Historical SQL artifacts; current schema belongs to SQLModel and Alembic |

## Quick start

Use Linux, Python 3.12+, Node.js 24, Docker Engine with Compose v2, GNU Make, Git
and curl. The installer pins Foundry tools, compiler and contract libraries; Docker
uses its own pinned Anvil image.

```bash
./scripts/install_dev.sh
source .venv/bin/activate
make setup
make contracts-build
make demo
make demo-scenario
```

Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)**. Use `govdemo1@solar.local` (producer/operator) or
`govdemo2@solar.local` (consumer). Read the generated `SEED_PASSWORD` privately from
`infrastructure/docker/.env`. Never commit that file or import local fixture keys
into a public-network account.

`make setup` starts services and runs migrations; `make demo` separately deploys and
commissions the local community. The scenario has been executed locally with
5 kWh injection, 3 kWh allocation, 0.003 ETH settlement and 3 SUN retirement.
[Getting started](docs/getting-started.md) covers verification, continuous simulation,
wallet setup, credentials and the distinction between bootstrap and plain seed data.

## Development and tests

```bash
make test                    # contracts, backend integration, IoT and frontend
python scripts/sync_abis.py   # check compiled contracts against application ABIs
```

Run these after activating the installed virtual environment. Browser tests also
need the development stack and Vite; see [development](docs/development.md).
Configuration is documented in [configuration](docs/configuration.md), operations
in [deployment](docs/deployment.md).

## Documentation

| Guide | Canonical subject |
| --- | --- |
| [Architecture](docs/architecture.md) | Components, trust boundaries and decisions |
| [Getting started](docs/getting-started.md) | Local installation and demonstration |
| [Configuration](docs/configuration.md) | Settings, defaults and secret handling |
| [Database](docs/database.md) | Actual SQLModel tables, relationships and migrations |
| [API](docs/api.md) | Authentication, routes, examples and OpenAPI |
| [IoT](docs/iot.md) | Commissioning, wire protocol, physics and quality |
| [Blockchain](docs/blockchain.md) | Contracts, authority, wallet calls and reconciliation |
| [Community settlement](docs/community-settlement.md) | Eligibility, allocation, money, SUN and corrections |
| [Deployment](docs/deployment.md) | Compose operations and Sepolia procedure |
| [Development](docs/development.md) | Tests, frontend conventions and documentation maintenance |
| [Verification](docs/verification.md) | Prior executed integration evidence and its limits |
| [Security](SECURITY.md) | Trust assumptions and unresolved security work |
| [Documentation audit](docs/documentation-audit.md) | Consolidation inventory, corrections and checks |

## Status and limitations

The complete local native ETH workflow is implemented and tested. Sepolia deployment
tooling exists, but no public deployment or MetaMask-extension end-to-end execution
is evidenced. Simulated telemetry is eligible only in opted-in local Anvil
communities; Sepolia requires commissioned physical sources. No calibrated physical
meter deployment, independent security audit or production readiness is claimed.

Native ETH P2P trading, public community discovery, profile editing, complete
participant evidence/event histories, automatic financial reversals and utility
billing integration are absent. Historical USDx/COPx and redemption code remains
separate; legacy settlement workers are disabled by default.

## License

No repository-wide license file is present. Individual source files and third-party
packages may carry their own notices; this README does not grant a new license.
