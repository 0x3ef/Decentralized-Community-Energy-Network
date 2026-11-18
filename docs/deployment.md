# Deployment and operations

The maintained runnable target is the local prototype in
[compose.prototype.yml](../infrastructure/docker/compose.prototype.yml). It is not
a hardened production deployment. Initial local setup belongs to
[getting started](getting-started.md); settings belong to
[configuration](configuration.md).

## Services and storage

| Service | Purpose | Host exposure in the prototype |
| --- | --- | --- |
| `timescaledb` | PostgreSQL 16 through TimescaleDB 2.17.2 image | Internal only |
| `redis` | Revocation, heartbeats, optional mail broker | Internal only |
| `mosquitto` | MQTT 2.0 broker, persistent messages | 127.0.0.1:1883 |
| `anvil` | Local EVM, chain 31337, instant transaction mining + 12-second empty blocks | 127.0.0.1:8545 |
| `migrate` | One-off reviewed Alembic upgrade | None |
| `api` | FastAPI under `/api/v1` | 127.0.0.1:8000 |
| `subscriber` | Standalone MQTT-to-SQL ingest | None |
| `worker` | Energy processing, native outbox, confirmed indexing | None |
| `frontend` | Built React application served by nginx | 127.0.0.1:8080 |
| `simulator` | Optional registered REALTIME direct MQTT overlay | None |

API/worker/subscriber wait for migration success and healthy dependencies. The
canonical image runs those processes as UID/GID 1000. API health is database
liveness; worker/subscriber health checks require fresh Redis heartbeat state.
The `migrate` service uses the configured image entry point and applies static
revisions; no application replica generates a migration.

PostgreSQL, MQTT, Anvil and simulation checkpoints use named volumes. The project
name is read from the original private env file and is never changed by recovery.
The lifecycle always includes both canonical Compose files, preventing simulator
containers from being stranded on a removed network. Stale network references
trigger one container-recreation retry while retaining named volumes.

Anvil is supervised by a small Python process in a pinned Foundry-based image.
It retains 128 historical states, disables historical disk spill, and mines
transactions immediately while adding empty blocks every 12 seconds. Every 30
seconds and on graceful shutdown, the supervisor obtains an RPC snapshot, validates
it, fsyncs a temporary file and atomically replaces `anvil.json`. The previous
completed checkpoint is retained as `anvil.previous.json`. A failed/incomplete
write cannot replace the completed file. Invalid current state falls back to a
valid previous checkpoint; two invalid files stop startup with a recovery message.
Snapshots have a 128 MiB ceiling and a free-space check; failures retain prior files.
Unexpected termination can lose transactions since the most recent checkpoint;
SQL/EVM reconciliation remains necessary. Container logs rotate at 3 x 10 MiB.
The original genesis timestamp/hash is persisted independently, duplicate
restart-generated block-zero headers are excluded on load, and the mining clock
resumes at current UTC time above the saved head. This preserves network identity
without leaving new blocks stuck near the original genesis time after restart.

## Builds and routine commands

```bash
make setup       # first local installation: build, migrate and commission
make up          # resume/update the complete application
make simulate    # complete application plus registered continuous simulator
make doctor      # containers, space, deployment and readiness
make backup      # verified private pg_dump archive
make down        # stop all canonical services, including simulator; retain volumes
```

[stack.py](../scripts/stack.py) is the single lifecycle implementation. Builds run
serially, API code is built once, and simulation never rebuilds dependency services
implicitly. Startup checks deployment state before starting application writers.
Missing contracts produce an actionable recovery error instead of normal startup
against stale addresses. A process lock prevents overlapping lifecycle commands.
Original credentials and existing records are never overwritten by initialization.
`make build` explicitly builds all images; `make clean` removes compiler artifacts
only and never removes Docker volumes. The legacy Docker Compose file and the
script that switched to a fresh SQL project have been removed.

The frontend is a multi-stage Vite/nginx image. Its public configuration is baked
at build time. nginx proxies `/api/` before static asset regexes and refreshes Docker
DNS so an API container's changed IP does not leave stale 502 responses.
Simulator/gateway images install pinned runtime dependencies from
`iot/requirements.lock` before copying code. Test runners, type checkers and
compilers are confined to the test stage, and code edits reuse the dependency layer.

Managed builds use an optional BuildKit `proxy_ca` secret; runtime clients mount a
combined trust bundle. Keep TLS verification enabled. Both `NO_PROXY` and `no_proxy`
exclude internal service hostnames while preserving configured external proxies.
Do not expose secret-bearing Compose configuration or provider errors in logs.

## Health, logs and troubleshooting

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/api/v1/openapi.json >/dev/null
```

Authenticated `/api/v1/system/status` exposes component readiness. Active operators
can read `/api/v1/communities/{community_id}/operations/status` for batch/job counts,
quality, indexed/confirmed height, lag and alerts. The frontend settings screen
displays these checks. Device health uses authenticated fresh telemetry, not merely
MQTT connectivity.

| Symptom | Investigation and response |
| --- | --- |
| Migration failure | Read the dedicated service error; verify schema revision and database access; never stamp or regenerate schema to hide a conflict |
| `InvalidPasswordError` during migration | Restore the original database credentials in `infrastructure/docker/.env` DATABASE_URL; container startup preserves them and changes only host/port. POSTGRES_PASSWORD initializes new volumes only; do not delete an existing volume or regenerate credentials |
| `/ready` 503 | Identify missing/degraded DB, Redis, RPC, worker or subscriber; liveness alone does not establish processing |
| RPC 403 or wrong chain | Check authorized network route, CA, proxy exclusions and chain ID; this is not a confirmed settlement |
| No device telemetry | Check commissioned public/internal UUIDs, active source/member/node/meter bindings, credential, exact topic ACL and broker TLS |
| No eligible interval | Check timestamps, exact processed boundaries, gaps/resets, quality and grace period; never fabricate missing energy |
| Unfunded allocation | Check own available ETH, consumer price ceiling and producer available SUN escrow; submitted evidence does not fund a vault |
| Pending or replaced transaction | Preserve hashes/attempts; wait for receipt depth and indexing, then use explicit reconciliation/replacement controls |
| Bootstrap identity/deployment mismatch | Preserve journals and review actual ownership/receipts; do not reset passwords or unlink wallets to force success |
| Missing contract after chain reset | Quarantine and reconcile; retain old history; never pay or mint again from stale projections |

Structured ingest logs expose persisted/duplicate/rejected counts, queue depth and
latency. Worker logs expose event/error types; raw exception arguments are withheld
by the configured formatter. Heartbeats expire after 90 seconds and become stale
after 30. A healthy worker can still have failed jobs requiring operator review.

Broker authentication/TLS provisioning is documented in [IoT](iot.md#broker-acls-and-tls).
The local fixed database credentials and anonymous broker must not be exposed as
a public production system.

## Repair unused local contracts on the same database

`make repair-demo` and `make recover-demo` are compatibility aliases for the single
same-database recovery command below. There is no isolated replacement database.

## Recover a local demo after lost Anvil state

If checkpoints are corrupt, or the node has no code at stored contract addresses:

```bash
source .venv/bin/activate
make recover
make doctor
```

This is an explicit LOCAL chain replacement, not recovery of lost blockchain
transactions. It uses the SAME Compose project, PostgreSQL volume, private
credentials, users, wallets, homes, devices and telemetry. No rows are deleted.
The command stops writers and the simulator, verifies a private PostgreSQL custom
archive under `.run/backups/<timestamp>/database.dump`, and retains original
configuration, encrypted wallets and deployment/scenario metadata beside it.
Do not publish these private archives. Large pre-existing corrupt Anvil copies
are not duplicated into every SQL backup; active node files are moved into
`/state/archive/<timestamp>/` inside the original Anvil volume.

After starting a fresh local node, the backend records an explicit
`local_chain_recoveries` audit with old bindings and original record states. Native
batches and wallet transactions are marked archived, indexed events become
noncanonical, and old signed operations are blocked from replay. Claims,
allocations, credits, telemetry and every other row remain retained. Active
statements exclude archived financial projections. Prior ETH/SUN balances,
payments and retirements are not recreated or presented as current balances.

The same fixture identities and original meter credentials are commissioned against
the new contracts. A new accounting cutoff prevents historical intervals from
issuing tokens again. Only new fully observed intervals may create new batches.
Recovery persists its in-progress marker and deployment journal so an interrupted
commissioning can resume on the same new chain. It checkpoints the contracts,
updates configuration, rebuilds the frontend, and starts the full app and simulator.
An intact fully deployed protocol is not reset. Nonlocal environments are refused.
The optional finite scenario also preserves cumulative meter baselines after
recovery. It refuses to reuse pre-recovery intervals and reports when the first
complete new interval plus its two-minute grace period becomes available.

If `/state` still contains a valid previous snapshot, normal startup can restore it
without a chain replacement. Back up SQL and EVM state together; a SQL dump alone
cannot reconstruct EVM contract storage, receipts or balances. Keep `.env` and
`.run/demo` when moving checkouts. The original `COMPOSE_PROJECT_NAME` must select
the same existing PostgreSQL volume; never use another project to hide old records.

## Sepolia deployment and commissioning

This is an explicit public-testnet procedure, not a claim that deployment occurred.
The local demo's automatic authority and impersonated accounts are prohibited here.

### Secure configuration and preflight

Compile with the pinned compiler (`make contracts-build`) and check ABIs with
`python scripts/sync_abis.py`. Copy
`infrastructure/docker/.env.sepolia.example` to the ignored `.env.sepolia` and enter
values securely. Do not paste keys into chat or commit them.

Required deployment settings: `SEPOLIA_RPC_URL`, `SEPOLIA_DEPLOYER_PRIVATE_KEY`,
`GOVERNANCE_PROPOSER_ADDRESS`, `GOVERNANCE_EXECUTOR_ADDRESS`, and `ORACLE_ADDRESS`.
Use a separate authorized backend signer (`BACKEND_PRIVATE_KEY`) corresponding to
ORACLE_ADDRESS. Governance/deployer and oracle accounts must be distinct. A multisig
or appropriate authorized contract may be the timelock proposer/executor.

Permit the RPC host in the execution environment's network settings, preserving
proxy and CA trust. Fund the deployer with enough Sepolia test ETH using an external
faucet or existing funded account; availability is not assumed. Backend oracle and
participant wallets also need their own test gas funds. No automatic faucet is used.

```bash
source .venv/bin/activate
set -a
source infrastructure/docker/.env.sepolia
set +a
scripts/deploy.sh COMMUNITY_UUID --network sepolia
# Inspect the preflight result, authorities and public output path, then:
scripts/deploy.sh COMMUNITY_UUID --network sepolia --broadcast
```

The first command does not transact. The broadcast command verifies chain 11155111,
checks a conservative gas budget, deploys the timelock, registry, SUN, settlement and
vault, and requires three confirmations per contract. The one-day minimum timelock
and challenge periods cannot be bypassed with local settings. Failed or timed-out
receipts do not produce a successful-deployment claim.

`.run/sepolia/deployment.json` stores public configuration, addresses, receipt block
hashes and pending transaction hashes. `.run/sepolia/governance-plan.json` contains
reviewable setup calldata. Keys and authenticated RPC URLs are excluded. A pending
deployment resumes receipt verification rather than deploying another copy.
Changed chain hashes/artifacts/configuration cause a stop and explicit review.
Do not remove a pending journal to retry a possibly submitted transaction.

### Community and protocol commissioning

1. Verify deployed bytecode/addresses independently and retain the receipt journal.
   Optional Etherscan source verification needs independently configured credentials;
   this runbook does not claim explorer verification happened.
2. Configure the confirmed registry/timelock addresses in the backend. A linked
   participant proposes the physical boundary and policy through the API and signs
   its registry proposal. A proposal does not grant authority.
3. Through the authorized timelock, transition PROPOSED -> UNDER_REVIEW -> APPROVED.
   Configure the positive wei/kWh price while APPROVED; the contract rejects price
   configuration after activation.
4. Review/schedule each setup operation from governance-plan.json: bind vault and
   protocol, grant SUN mint authority to CommunitySettlement, revoke the timelock's
   initial minter role, and grant only ORACLE_ROLE / SETTLEMENT_ROLE to the backend.
   Execute only when the actual timelock reports ready after its delay.
5. Activate with an explicitly appointed operator. Synchronize the confirmed
   CommunityTransition receipt via `/{community}/governance/sync`. Register the native
   deployment through `/{community}/native-deployment`; the backend validates exact
   governed protocol bindings.
6. Approve memberships, nodes and meters, synchronize their states, and issue device
   credentials. Use MQTT authentication/ACLs and TLS when traffic leaves loopback.
   Sepolia requires commissioned PHYSICAL sources. Simulated evidence is rejected
   there even when simulation consent is set; simulation settlement is local-only.
7. Have each user connect/verify their own wallet, deposit native ETH or approve and
   escrow SUN as needed. The server never signs participant payments or withdrawals.
8. Review an evidence commitment; finalize eligible batches through authorized
   governance after the challenge period. Automatic backend processing may then
   reserve/deliver funded allocations. Finalization is not delegated to an ordinary
   operator. Retirement requires delivered, finalized consumption and SUN allowance.

### Run the stack against Sepolia

Set `COMMUNITY_REGISTRY_ADDRESS`, `GOVERNANCE_TIMELOCK_ADDRESS`, and
`NATIVE_SETTLEMENT_START_BLOCK` (the earliest confirmed deployment block from the
journal). Configure JWT/database/MQTT settings appropriately. Use an isolated runtime host
and checkout, not the existing local fixture stack. The base backend also loads
`infrastructure/docker/.env`; securely prepare that runtime file with the intended
public-service credentials, including JWT and broker settings. `--env-file` alone
controls interpolation and does not replace the service env-file. Never assume local
JWT/database credentials became public-service credentials automatically. The public browser RPC
`VITE_SEPOLIA_RPC_URL` is optional and must not contain a private provider credential.

The following deployment command is source-checked; public execution has not been
performed because RPC/funded authority configuration is absent.

```bash
docker compose --env-file infrastructure/docker/.env.sepolia \
  -f infrastructure/docker/compose.prototype.yml \
  -f infrastructure/docker/compose.sepolia.yml up -d --build --wait
curl -fsS http://127.0.0.1:8000/ready
```

The overlay explicitly selects testnet, chain 11155111, three backend confirmations
and the Sepolia RPC. The base's loopback Anvil dependency is unused; its presence
cannot change the expected public chain. The local bootstrap refuses this environment.
Use persistent database state and allow the indexer to catch up from deployment.

In MetaMask add/switch to Sepolia (11155111). Confirm contract addresses and test ETH
value; wallet ETH is distinct from deposited/reserved/earned ETH. SUN approval to the
vault is distinct from approval to the retirement contract. Native P2P trading is not
supported by these contracts. A confirmed chain receipt still needs backend indexing
before the UI's canonical financial statement is updated.

A full public acceptance test must record actual deployment and user transaction
hashes, confirmation depth, governance execution, meter quality, allocation evidence,
retirement and withdrawal results. If credentials, funding or network access are
missing, report that blocker rather than presenting local results as Sepolia proof.
