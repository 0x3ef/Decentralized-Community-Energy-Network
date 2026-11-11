# Community energy allocation and settlement

The FastAPI backend constructs native ETH batches and drives the governed
contracts through the community worker. Historical ERC20 deployments,
payments and denominations remain separate. No historical obligation is relabelled
as ETH and no legacy marketplace payment is created by this pipeline.

## Operating sequence

1. Deploy and approve the native protocol as described in
   [blockchain protocol](blockchain.md). Verify the registry's protocol
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
service transactions share a PostgreSQL chain-ID/genesis/signer nonce lock and journal.
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

## Participant and operator interfaces

The [API guide](api.md) owns the route reference. Participants can read their own
claims, allocations, funding and statement; operators can calculate, inspect jobs,
reconcile and explicitly retry terminal failed work. Unsigned native preparation
supports deposits, withdrawals, SUN escrow, retirement and reservation cancellation.
Governance preparation returns registry schedule/execute calls, not an automatic
batch finalization. Full participant evidence manifests and batch-finalization
preparation remain incomplete.

## Worked and executed local scenario

At 5,000 Wh eligible injection and 3,000 Wh eligible demand, allocation is 3,000 Wh
and unallocated injection is 2,000 Wh. With approved price 10^15 wei/kWh:

```text
due_wei = ceil(3000 * 10^15 / 1000) = 3 * 10^15 = 0.003 test ETH
```

After governance finalization, the injection claim issues 5 SUN. The producer
approves and escrows those credits. A consumer deposit of 0.01 ETH funds the
0.003 ETH reservation. Execution delivers 3 SUN and credits 0.003 ETH producer
earnings, leaving 0.007 ETH consumer available funds and 2 SUN producer escrow.
The consumer separately approves and retires 3 SUN; supply becomes 2 SUN and no
second ETH payment occurs. The producer withdraws the 0.003 ETH earnings.

This complete scenario was executed locally, including a worker restart and
idempotent replay; see [verification](verification.md) and the retained
[local evidence](evidence/local-native-scenario.json). It is not a public testnet
transaction or a physical-energy delivery assertion.

## Status and correction boundaries

A batch starts PREPARED; contract submission is CHALLENGEABLE, then governance
may finalize or reject it. Finalized evidence is distinct from an allocation's
funding state (such as UNFUNDED or SUN_UNAVAILABLE), reservation, and SETTLED
delivery. SQL statuses are projections of these stages rather than a single
"paid" flag. A retirement claim becomes RETIRED only after confirmed burning.

Community suspension prevents new issuance and settlement while preserving safe
exits. Consumers can cancel reservations on suspension or expiry; they cannot
withdraw reserved funds directly. Used batch corrections and paid entitlement
reversals require explicit review; there is no automatic correction endpoint.
Contradictory authenticated evidence quarantines intervals and blocks new worker
operations. Existing chain payments remain actual history.

Worker configuration defaults and source settings are centralized in
[configuration](configuration.md); signing and canonical recovery are in
[blockchain](blockchain.md).
