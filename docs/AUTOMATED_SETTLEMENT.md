# Automated community settlement backend

The FastAPI backend now constructs native ETH batches and drives the Prompt 1
contracts through the existing community worker. Historical ERC20 deployments,
payments and denominations remain separate. No historical obligation is relabelled
as ETH and no legacy marketplace payment is created by this pipeline.

## Operating sequence

1. Deploy and approve the native protocol as described in
   [NATIVE_ETH_PROTOCOL.md](NATIVE_ETH_PROTOCOL.md). Verify the registry's protocol
   binding, fixed wei/kWh price, operator, active members, nodes and meter bindings.
2. Authenticate device telemetry with registered credentials. The energy worker
   differences cumulative counters, rejects duplicates/resets/spikes and finalizes
   closed UTC intervals after a two-minute grace period.
3. The native worker discovers recent finalized intervals and creates one immutable
   batch per community/start/end. An operator may also request calculation through
   the API. PostgreSQL advisory locks serialize competing requests and policy
   snapshots; database uniqueness independently prevents duplicate intervals.
4. The worker submits the Merkle commitment using its authorized oracle signer.
   A submitted transaction is not a finalized batch. Governance must finalize the
   batch after the contract challenge period; the worker never impersonates it.
5. On confirmed finalization, issuance claims mint SUN through CommunitySettlement.
   Claims link the existing energy credit and interval records. Consumers explicitly
   deposit ETH; producers explicitly approve and escrow SUN using their own wallets.
6. The worker checks balances and price limits, reserves approved ETH/SUN allocations,
   and executes reservations. Inadequate funding remains UNFUNDED; inadequate producer
   escrow is SUN_UNAVAILABLE. A reservation is distinct from settled delivery.
7. Confirmed execution credits producer earnings and delivers SUN. Consumers use
   their returned retirement proof and a separate SUN burn allowance to retire the
   complete delivered node allocation. Retirement never creates another payment.
8. Producers withdraw their earnings with their own wallets. The backend tracks
   transaction references and confirmed contract events; it never increments a
   deposit balance in SQL as a substitute for ETH.

## Accounting policy and evidence

The prototype requires one active authoritative smart meter per node and processed
samples at both exact interval boundaries. Missing boundary coverage excludes the
node; it is not extrapolated into a complete interval. Export is bounded by verified
meter export, not gross PV generation. Import/export is netted for each interval;
self-supplied energy across one wallet's multiple nodes is also netted before
allocation. A configured loss factor reduces eligible injection with integer Wh
floor rounding. This is an accounting loss allowance, not a topology/power-flow
simulation. No temporal banking, network capacity model or physical delivery claim
is introduced.

Allocation uses proportional largest remainder rounding, with stable node IDs for
ties, independently for producer and consumer totals. Stable transportation pairs
join those totals. No wallet pays itself; producer contributions and consumer caps
cannot exceed their verified net quantities. Every pair pays
`ceil(Wh * price_wei_per_kwh / 1000)`. Consumer dues and producer receivables are the
same pair sums, so money balances exactly. Splitting into several pairs may add up
to one wei per pair relative to rounding a single combined amount; no fee or
unassigned residual is created. API wei quantities are decimal integer strings.

Each batch records its immutable policy snapshot, interval, totals, price-derived
obligations, physical intervals, node/meter IDs, telemetry IDs, canonical payload
hashes, calculation version, netting rule, and Merkle root. Sorted-pair,
double-keccak ABI leaves exactly match the contracts (kind 0 issuance, 1 retirement,
2 financial allocation). Proofs are persisted, not regenerated from mutable state.
The native claim links the existing EnergyCredit; its issued state follows confirmed
contract claims. SQL allocations retain source and demand interval foreign keys.

Policy rows are immutable snapshots keyed by community and approved policy hash.
Price comes from the registry, not a client or a fixed fiat conversion. The current
registry permits configuring price while APPROVED and freezes it on activation.
A different price/policy after activation requires explicit governance review and
a new supported deployment; the backend does not rewrite earlier snapshots.
Used batches cannot be silently corrected. This prototype has no automatic paid
entitlement reversal or financial correction endpoint.

## Persistence and worker recovery

`native_settlement_policies`, `native_settlement_batches`,
`native_settlement_claims`, `native_interval_allocations`,
`native_wallet_transactions`, `native_indexed_events` and `native_sync_cursors`
are new native protocol entities, not alternate mappings of existing tables.
They reuse communities, memberships, homes, devices, telemetry, energy intervals,
credits, OutboxEvent and ChainOperation. Alembic revision
`20261110_native_pipeline` is a static reviewed schema migration. Startup does not
create migrations or delete historical records. Downgrading financial history
requires explicit archival rather than automatic table deletion.

A calculation and its outbox job commit together. Before any broadcast, workers
commit the raw signed transaction, hash, nonce and job lease. All legacy and native
service transactions share the same PostgreSQL signer/chain nonce lock and journal.
A crash before/after broadcast reuses the same signed bytes. Leases expire after
30 seconds; transient errors use bounded exponential retry. An operator can inspect
job errors. A confirmed reverted transaction is terminal FAILED and requires an
explicit retry job; its original operation remains in history. Fee replacement
uses the existing operator replacement endpoint, keeps nonce/value/calldata, and
preserves prior signed attempts. Native operation listings provide operation_id.

The confirmed event cursor advances transactionally with projections, including
empty block ranges. Event replay has a chain/transaction/log/block-hash unique
identity. Before each pass, canonical block hashes and service receipts are audited.
Orphaned events remain retained with canonical=false; batches and wallet references
are marked for reconciliation. Projections are rebuilt from confirmed contract
state, so orphaned retirement/delivery is not counted. Service jobs whose receipts
were orphaned replay their journalled transaction, not a new entitlement. User
transactions require the user's own retry; the worker never signs for them.
Reconciliation aborts if the canonical chain changes during its pass.

## APIs

All paths below are under `/api/v1/communities`. JWT authentication is required.
Current community/member authority is checked against the registry. Personal
allocations and claims are restricted to the requesting participant; funding
responses disclose only that participant's own vault/escrow balances. Aggregate
batch totals are visible to authorized community members. Oracle job errors and
retry actions require the appointed operator. Raw signed bytes are never returned.
List endpoints use bounded `limit` and `offset`; history also supports `status`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/{id}/settlements/calculate` | Operator calculates an aligned `interval_start` |
| GET | `/{id}/settlements` | Batch overview and history |
| GET | `/{id}/settlements/{batch}` | Interval totals, unallocated injection and obligations |
| GET | `/{id}/settlements/{batch}/allocations` | Own pair obligations and funding/settlement states |
| GET | `/{id}/settlements/{batch}/claims?kind=1` | Own compensation eligibility/history and exact claim proofs |
| GET | `/{id}/allocations/{allocation}/funding` | Funding/escrow preflight and confirmed own balances |
| GET | `/{id}/settlement-statement` | Own dues, settled entitlements, claimable and withdrawn earnings, retirement |
| GET | `/{id}/settlement-policy` | Governed price and immutable policy rules |
| GET | `/{id}/settlements/{batch}/operations` | Operator's durable job/transaction status |
| POST | `/{id}/settlements/{batch}/reconcile` | Operator requests canonical event reconciliation |
| POST | `/{id}/settlements/{batch}/jobs/{job}/retry` | Explicitly retry a terminal FAILED operation |
| POST | `/{id}/native/transactions` | Track own hash and declared action after function/sender/target validation |
| GET | `/{id}/native/transactions` | Own pending/confirmed/failed/reorganization status |
| POST | `/{id}/memberships/apply` | PENDING local membership application, grants no authority |
| POST | `/{id}/memberships/sync` | Synchronize own membership from confirmed registry state |
| POST | `/{id}/governance/prepare` | Unsigned review, approval, activation, suspension, membership, node, meter or price calldata |

The existing native wallet read/prepare endpoints still handle explicit deposits,
withdrawals, SUN approval/escrow, retirement and consumer cancellation of an
expired or suspended reservation (`cancel` with its claim_id). Native wallet balances now include
the confirmed block number. Claim responses include chain_node_id and chain_meter_id
in bytes32 form for the retirement request. A `retirement_eligible` claim indicates
funded SUN delivery; the user must still own the credits and approve the burn.

Governance preparation checks the registrar or the configured timelock's proposer
role. With a timelock it returns separate unsigned schedule/execute calldata,
operation ID and minimum delay. A supplied salt makes preparation repeatable.
Scheduling is not execution, and execution is not a database authority update until
the existing governance receipt synchronization verifies canonical confirmations.
Detailed node/meter physical verification remains the registrar's responsibility.

## Configuration and verification

- `NATIVE_SETTLEMENT_ENABLED=true`: enable the native stage in community_worker.
- `NATIVE_SETTLEMENT_LOOKBACK_HOURS=24`: bounded automatic discovery (1–168 hours).
- `NATIVE_SETTLEMENT_INTERVAL_LIMIT=200`: per-community scan limit; explicit API
  calculation can backfill older intervals.
- `NATIVE_SETTLEMENT_START_BLOCK=0`: initial event scan bound. On Sepolia, set this
  to the earliest relevant deployment block to avoid scanning the entire chain.
- `GOVERNANCE_TIMELOCK_ADDRESS`: approved timelock for governance preparation.
- Existing RPC, confirmation-depth, registry and service signer settings still
  apply. The signer needs oracle/settlement authority and test ETH for gas.
  No user private key is requested or stored.

Run `scripts/test_backend.sh -q`, `make test-contracts`, and `scripts/test_iot.sh -q`
using the installed development environment. The integration test deploys real
contracts and exercises authenticated counter differencing, exact obligations,
concurrent calculation, crash recovery, underfunding, escrow, delivery, replay,
retirement, withdrawals, timelock preparation and an Anvil snapshot reorganization.
No public Sepolia broadcast or independent security audit is implied.
