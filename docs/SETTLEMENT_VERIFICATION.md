# Backend settlement verification — 2026-11-10

Implemented the native backend pipeline against the committed CommunityRegistry,
CommunitySettlement and NativeSettlementVault ABIs. The test environment uses a
fresh disposable PostgreSQL database per run, Redis, MQTT and local Anvil. Existing
historical ERC20 tests still run; their units and records have not been converted.

## Executed checks

| Check | Result |
| --- | --- |
| Backend suite | 28 passed |
| Foundry suite | 38 passed, including 256 liability fuzz runs |
| IoT suite | 66 passed; 83.28% coverage |
| Ruff on new settlement modules and tests | Passed |
| Static Alembic upgrade through native pipeline | Passed on fresh test DB and existing development DB |
| Rebuilt development backend | API health and OpenAPI checked locally |

The new integer engine tests run 200 deterministic random supply/demand scenarios,
check conservation and input-order independence, large integer obligations,
per-pair rounding, and sorted Merkle proofs for even and odd tree sizes.

The native integration test uses real PostgreSQL locks, authenticated MQTT envelope
validation, actual EnergyProcessor counter differencing, actual Solidity deployments,
and actual signed/broadcast service transactions. It verifies:

- Invalid device credentials are rejected and duplicate telemetry is ignored.
- Missing exact boundary evidence cannot create a batch, even when an aggregate
  interval is already marked FINALIZED.
- The worker discovers an eligible interval and calculates the batch without
  operator API intervention; repeated and concurrent API calculations reuse it.
- Consumer role cannot calculate or inspect operator jobs; participant claim and
  funding reads exclude other participants' private data.
- A saved signature survives a pre-broadcast crash and resumes with the same hash.
- Governance finalization precedes issuance; actual issuance is 5 SUN for 5 kWh.
- 3 kWh allocation leaves 2 kWh unallocated and owes exactly 3,000,000,000,000,000 wei.
- A 0.001 ETH deposit cannot settle the 0.003 ETH obligation; no earnings appear.
- A reservation signed while funded but mined after withdrawal reverts without
  paying anyone; it remains FAILED with its original transaction history. An explicit
  operator retry creates a new job and nonce after fresh funding.
- After explicit additional funding and producer SUN escrow, ETH and SUN are
  reserved and actual execution delivers 3 SUN with 0.003 ETH claimable earnings.
- Repeated worker passes and event replay do not duplicate claims or payments.
- Retirement burns 3 SUN, rejects duplicate consumption and creates no payment.
- Reverting an Anvil snapshot after execution/retirement invalidates orphaned
  events, restores the reservation projection and marks user transactions for
  reconciliation. The worker replays the saved transaction. Retirement requires
  a fresh user action; final supply is 2 SUN and producer entitlement remains 0.003 ETH.
- Producer withdrawal clears earnings; the remaining 0.007 ETH consumer deposit
  remains an actual vault liability, fully backed on chain.
- An ordinary operator cannot prepare registrar actions. A timelock proposer can
  obtain valid unsigned schedule/execute calldata. Scheduling does not suspend
  the community. Execution followed by canonical receipt synchronization does.

## Practical limits

All execution was local. No Sepolia transaction was broadcast, no real-money
settlement is represented and no independent security audit was performed.
The test has a zero-delay timelock for deterministic execution; deployment scripts
retain their 24-hour governance delay. The deployment contract challenge window
is likewise not shortened by the backend.

Oracle/registrar authorization and device credentials do not establish physical
measurement truth. Physical commissioning and evidence review remain trusted
responsibilities. Conservative boundary coverage can leave intervals ineligible;
no extrapolated energy or artificial funding is introduced to improve the demo.

The old ERC20 event indexer scans bounded 500-block pages. Its integration test now
drains those pages before asserting confirmation, so a reused Anvil chain with
thousands of prior test blocks is handled correctly. The new native indexer uses
its own durable cursor and confirmed block ranges.
