# Verification report

Verified on 10 November 2026 in the attached Linux cloud environment. Results below
refer to commands that were executed, not proposed checks.

## Passing checks

| Check | Result |
|---|---|
| `scripts/install_dev.sh` with the workspace tooling/venv paths | Completed; package installation, checksum verification, contracts, frontend build and lint |
| Foundry / Solidity 0.8.24 | 20 tests passed, none skipped; partial-fill fuzz test ran 256 cases |
| `scripts/test_backend.sh -q --tb=short` | 9 tests passed, none skipped, against dedicated real PostgreSQL 16, MQTT, Redis and Anvil services |
| `scripts/test_iot.sh -q` | 44 passed, none skipped; 82.26% coverage against the unchanged 80% gate |
| Frontend TypeScript + Vite build and oxlint | Passed; bundle-size warning remains advisory |
| Backend and frontend Docker image builds | Passed with TLS verification and managed CA mounts |
| Fresh TimescaleDB deployment | Reviewed Alembic migrations applied successfully; API/subscriber/worker running, frontend healthy, both HTTP health responses verified |
| Existing-schema upgrade | Inserted a sentinel user at the original revision, upgraded to head, verified the same user remained |
| `alembic check` on the upgraded schema | No new upgrade operations detected |
| Authenticated browser smoke test with Chromium | Loaded Community Settlement, created a community through the real API and verified the displayed result |
| Python undefined-name/unused-import check on the new backend modules | Passed |
| `git diff --check` | Passed |

## Mandatory lifecycle evidence

The backend end-to-end test registers a producer, consumer, homes, node memberships,
authorized smart meters, an inverter and battery. It publishes actual MQTT QoS1
samples with registered UUID identities and credentials. The subscriber persists
them into PostgreSQL before acknowledging delivery.

The accounting interval has 10 kWh generation, 6 kWh producer consumption, 1 kWh
battery discharge and 5 kWh authoritative grid export. Eligible issuance is 5 SUN,
not 10 SUN from generation or 4 SUN inferred without the battery/export readings.
The consumer has 3 kWh verified grid withdrawal.

After explicit approval, concurrent workers process the outbox. A deliberately
pending mint is fee-replaced with identical nonce/calldata and both attempts kept
in durable history. The confirmed mint and source accounting commitment are
verified from contract events. The consumer receives 2,000 simulated USDx, purchases
3 SUN at 450 USDx/SUN and pays exactly 1,350 USDx in the same EVM transaction.
Both token Transfer events are verified before recording payment.

Competing idempotent compensation requests reserve only one allocation. A second
request exceeding the same withdrawal is rejected. The consumer approves and
burns 3 SUN; confirmed-event synchronization discovers the user-signed retirement,
verifies its evidence and burn log, and marks 3 kWh compensated.

Final assertions: producer 2 SUN and 1,350 USDx; consumer 0 SUN and 650 USDx;
SUN total supply 2; compensated energy 3 kWh. Reconciliation calls are idempotent.
The database rejects updates to ledger history. A subsequent test-chain rewind
moves affected confirmed records to reconciliation and appends reorganization
entries instead of retaining false confirmations.

Other checks cover invalid meter credentials, duplicate telemetry, late readings,
community isolation, receipt reverts, noncanonical block hashes, insufficient
confirmations, RPC timeout, wallet challenge replay, unauthorized API access,
order expiration/cancellation, membership restrictions, price-time selection,
duplicate issuance and retirement, insufficient payment and production faucet
rejection.

## Limits and remaining work

This validates the local technical prototype. It does not establish legal energy
retail authorization, real-money payment functionality, independent smart contract
security certification or readiness for a public production network.

The automated browser check covers authenticated API/UI behavior. A browser
wallet extension was not driven through a full user-signing demonstration;
contract execution, user-specific callers, allowance checks and wallet challenge
signatures were tested separately. A manual extension demonstration remains useful.

The former off-chain unreserved order matcher is read-only; use the dual-token
community contract and Community Settlement page for new transactions. BUY limit
orders, temporal banking and cross-community fungibility are intentionally disabled.
Legacy dashboard screens and optional email/password-reset delivery have not been
fully verified. The default login destination is the verified community workflow.

Failed/unknown allocations remain reserved until explicit accounting reconciliation.
The prototype detects reorganizations and preserves evidence, but does not create
automatic economic reversals or provide an operator reconciliation UI. Confirmed
history audits currently scan stored records; large deployments need bounded
retention/indexing and operational monitoring. Gas replacement is explicit rather
than an automatic fee policy.

Meter credentials are intended only for the loopback-bound local broker. Deployment
to an untrusted network requires TLS and broker identity/ACL administration; the
application's credential/topic checks remain necessary in addition to broker ACLs.

No external credentials or access blockers remain for the verified local workflow.
The earlier onboarding draft service failed to save environment configuration;
this coding deliverable does not claim that reusable cloud settings were saved or
published. Installation and startup commands are retained in repository scripts.


## Governed native ETH protocol, 2026-11-10

Executed locally: 38 Foundry tests (including 256 fuzz runs for vault liabilities),
18 backend tests against PostgreSQL/Redis/Anvil, 66 IoT tests with 83.28% coverage,
15 frontend tests, TypeScript/Vite production build, and 2 Chromium browser tests
against the running API. Fresh test databases migrate through native vault schema;
the development stack migration also completed. Governance API tests deploy real
TimelockController, registry, SUN, settlement and vault contracts, verify deployment
approval, deposit native ETH through prepared user calldata, and preserve safe
withdrawal after suspension. Browser tests cover proposal submission, disabled
unconfigured deposits, protected routes and mobile navigation.

No public Sepolia broadcast or independent audit was performed. Verifier batch
construction, governance scheduling and allocation reservations use direct
contract tooling; no automated physical-truth oracle is claimed. See
[NATIVE_ETH_PROTOCOL.md](NATIVE_ETH_PROTOCOL.md) for exact trust assumptions.
