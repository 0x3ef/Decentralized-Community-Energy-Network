# Solar Energy Market

[Current IoT protocol](docs/DEPIN_IOT.md) · [IoT verification](docs/IOT_VERIFICATION.md):
community-bound v2 telemetry, explicit simulation provenance, quality audits and TLS ACLs.

**Current governed protocol:** SUN energy credits plus native Anvil/Sepolia test ETH.
Community creation grants no operator privileges. See [native ETH protocol](docs/NATIVE_ETH_PROTOCOL.md)
for deployment, authority, API interactions, tests and limitations. The
[automated backend pipeline](docs/AUTOMATED_SETTLEMENT.md) covers interval allocation,
durable workers, ETH obligations and participant APIs. The earlier
USDx workflow below is historical compatibility documentation and must not be
used to bootstrap a new governed deployment.

A local development prototype for community energy accounting, SUN credits,
atomic SUN/USDx trading, and consumption compensation. Electricity is delivered
by the physical network; token transfers change accounting rights only.

**1 SUN = 1 verified eligible kWh by default. USDx is an unbacked simulated
Colombian peso payment token, with no redemption promise or real monetary value.**
The symbol is retained from the supplied specification; it does not denote real
US dollars. SUN uses 18 decimals; USDx uses 6. Each community has its own SUN,
marketplace and compensation deployment so credits cannot cross communities.

## Install

Use Python 3.12+, Node 24, Docker with Compose, Git, curl, and a Linux x86-64
machine for the compiler installer. Existing cloud tasks already have isolated
checkouts; do not create a Git worktree unless explicitly requested.

```bash
./scripts/install_dev.sh
source .venv/bin/activate
make setup
```

Installation preserves TLS verification, checks the Solidity compiler against
its official checksum, uses pinned Foundry/OpenZeppelin versions and the frontend
lockfile, and installs the canonical backend package. `make setup` creates fresh
local credentials only if no `.env` exists. It runs the reviewed Alembic migrations
through one dedicated service, then starts TimescaleDB, Redis, Mosquitto, Anvil,
API, subscriber, worker and frontend. It never generates migrations at startup.

Local checks (no public preview is required):

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8080/health
make ps
```

The development frontend is also available with `cd apps/frontend && npm run dev`.
Use the **Community Settlement** page for the SUN/USDx lifecycle. Other dashboard
screens are retained from the earlier prototype; financial redemption is separate
from energy compensation.

## Community setup

The interactive API documentation is served at `/api/v1/docs`. Authenticate with
`POST /api/v1/auth/signup` and `/auth/login`; use the access token as a Bearer token.

1. `POST /api/v1/communities` with `name`, optionally `sun_per_kwh` and
   `loss_factor`. The creator becomes a community operator. The conversion and
   loss policy are fixed for that community. Only same-interval matching is
   supported; temporal banking is disabled.
2. Register other users with `/auth/signup`. The operator adds them using
   `POST /communities/{id}/members` with their `user_id`.
3. Members create homes through `POST /home/`. Operators register the homes as
   authorized nodes through `POST /communities/{id}/nodes` with `home_id`.
4. Members register meters through `POST /device/device`. Operators authorize
   them through `POST /communities/nodes/{node_id}/meters` with `device_id` and a
   fresh random credential of at least 32 characters. Only one authoritative meter
   per channel is allowed for each node.
5. Link a user wallet with the signed challenge endpoints
   `/communities/wallet/challenge` and `/communities/wallet/verify`, or use the
   browser page. The backend never requests users' private keys.
6. Deploy the community's contracts:
   `scripts/deploy.sh COMMUNITY_UUID`. This uses the dedicated local backend
   authority from the ignored environment file and prints only public addresses.
   Register that JSON with `POST /communities/{id}/deployment`.
7. Queue membership authorization using
   `POST /communities/{id}/members/{user_id}/sync`. The worker verifies the
   resulting contract event. Suspension is available through the matching PATCH
   endpoint and queues on-chain revocation; allow it to confirm before relying on
   revocation for trades.
8. Publish authenticated cumulative meter samples. The CLI
   `scripts/publish_meter_sample.py --help` accepts registered UUID identities,
   cumulative kWh, sequence and timezone-aware timestamp. Supply the credential
   in `DEVICE_CREDENTIAL`, not in command arguments. Publish a baseline and
   interval-aligned subsequent readings. Query
   `/communities/meters/{device_id}/telemetry` for acceptance status.
9. The worker computes deltas and closes intervals after a two-minute late-arrival
   allowance. Approve eligible credits with
   `POST /energy/credits/{credit_id}/approve`. Approval, outbox creation and audit
   entries share one database transaction. Issuance status is exposed at
   `/communities/credits/{credit_id}/issuance`.
10. The browser signs SUN escrow approval, a SELL order, USDx payment approval,
    and a purchase. Reconcile the transaction through
    `/communities/{id}/trades/reconcile`. Only confirmed receipts containing both
    corresponding token transfers establish payment.
11. Reserve compensation through `POST /communities/{id}/compensations` using
    source/withdrawal interval UUIDs, integer `energy_wh`, and an idempotency key.
    Wait for worker authorization, approve the compensation contract's SUN
    allowance, and sign `retire(keccak256(request UUID))` with the consumer wallet.
    Confirm through `/communities/compensations/{request_id}/confirm`.
12. Read `/communities/{id}/statement` and `/ledger`. They distinguish verified
    energy, reserved allocation, confirmed compensation, and simulated payments.

The faucet is restricted to the contract's `FAUCET_ROLE`, local chain IDs 31337
or 1337, and a per-call limit. It is not a payment gateway. The local backend
operator may fund demo wallets by signing `MockUSD.faucet`; users never receive
SUN by depositing money.

## Verification

Run the backend suite against its dedicated disposable PostgreSQL, MQTT, Redis
and Anvil instances, separate from development services:

```bash
source .venv/bin/activate
./scripts/test_backend.sh
./scripts/test_iot.sh
.dev-tools/node_modules/.bin/forge test --root contracts --use .dev-tools/solc-0.8.24
cd apps/frontend && npm run build && npm run lint
```

The backend end-to-end test sends actual MQTT messages, persists and processes
meter readings, issues 5 SUN, trades 3 SUN for 1,350 of 2,000 USDx, retires 3 SUN,
and checks the final supply, balances, payment evidence and energy statement.
It also tests concurrent workers/reservations, idempotency, community isolation,
late readings, append-only ledger enforcement and a local EVM reorganization.
The reorganization test intentionally rewinds **only the disposable test chain**.
Never run it against a shared development or real network.

See [verification](docs/VERIFICATION.md), [accounting and settlement](docs/COMMUNITY_ACCOUNTING.md),
and [implementation architecture](docs/PROTOTYPE_ARCHITECTURE.md) for evidence and boundaries.

This is a technical and academic prototype. Deployment requires independent
review of applicable CREG, UPME, network operator, metering, consumer protection
and financial requirements. No regulatory authorization is implied.

## SQLModel demo seed

The stale raw SQL fixtures have been replaced by `src.seed`, which imports the
actual database models. Apply migrations, explicitly set DATABASE_URL for your
local development database, supply SEED_PASSWORD (12+ characters) and optionally
SEED_DEVICE_KEY (32+ characters), then run `./scripts/seed_db.sh` from the backend
virtual environment. See [seed instructions](database/seeds/README.md).

The generated registry covers all 15 sensors across five simulator homes and can
be passed directly to DEVICE_REGISTRY. Device credentials are written only to the
private output directory, never source control or logs. Seeds do not create token
balances, approved credits or verified wallets.
