# Community energy, credits and settlement

## Metering and intervals

Each node is associated with an existing Home and its owner, an active community
membership, and authorized Device rows. Cumulative values use integer Wh after
Decimal conversion. The authoritative grid-export counter determines injection;
solar generation alone never establishes issuance eligibility. Grid imports
establish eligible withdrawals, including consumer-only homes.

Samples use registered device/home UUIDs, sensor type, monotonic sequence,
UTC measurement/reception times, and a credential whose SHA-256 digest is stored
in meter_authorizations. MQTT topics must match the authorized identities. The
subscriber strips credentials before persistence, rejects future/stale samples,
and deduplicates using the existing device/sequence unique constraint. QoS1
messages are acknowledged after database commit; a persistent broker session
retains unacknowledged work over subscriber failure. Local broker access is
loopback-only; credentials must not be sent over an untrusted plaintext network.

Counter resets establish a new baseline without issuance. Out-of-order samples,
cross-interval gaps and finalized-interval late changes are rejected from energy
processing, retained for investigation, and do not block other samples. The
prototype uses UTC-aligned 15-minute intervals and a two-minute finalization lag.
A cumulative delta crossing an unobserved interval boundary is not interpolated.
Operators must investigate missing data rather than fabricate energy.

Battery charging and discharging are integrated from consecutive power samples
using an explicit trapezoidal rule within one observed interval, rounded down to
integer Wh. These are estimated integrals of measured power, separately labeled
from cumulative meter deltas. EnergyPowerSnapshot records are retained separately from
energy counters. Battery flows are not independently eligible for new credits;
authoritative export metering remains the issuance boundary. No physical loss is inferred from a
balance difference. The default accounting loss factor is explicitly zero.
A configured nonzero loss factor is an allocation derating policy, not a claim
that a physical loss was measured.

## Policy and provenance

The default conversion is 1 SUN/kWh; a positive community-specific conversion
can be set on creation. The supported temporal policy is SAME_INTERVAL. Injection
and withdrawal intervals must have identical UTC bounds. No temporal banking or
cross-community compensation is enabled. Independent SUN contract deployments
separate community credit provenance, while generic ERC-20 transfers remain
ordinary ownership transfers inside each deployment.

EnergyCredit uses existing states PENDING -> APPROVED -> ISSUANCE_PENDING ->
ISSUED, with REJECTED/FAILED terminal paths. MEASURED/VALIDATED/ELIGIBLE are
represented by persisted telemetry, finalized interval quality and credit
creation; signed submission and confirmation are represented separately by
community_chain_operations. They must not be inferred from a transaction hash.

Issuance IDs are keccak256 of the credit UUID text. The contract rejects duplicate
IDs. After confirmed issuance, the outbox anchors a deterministic SHA-256
commitment containing community, credit, interval, quantity and ordered source
measurement IDs/payloads. Each source credential has already been stripped.
The anchor cannot be overwritten. Raw telemetry stays off-chain.

## Trading and payment

SELL orders escrow SUN. Price is USDx base units per whole SUN: with USDx's six
decimals, 450 USDx/SUN is `450000000`. SUN quantity uses 18 decimals. Quotes use
ceiling division to prevent free fractional token dust. Purchases atomically
transfer USDx from buyer to seller and SUN from escrow to buyer, or revert both.
The contract supports cancellations, expiration, partial fills, membership
checks and price-time matching. The active community book is capped at 128 orders;
expired orders can be cleared with expireOrder, returning escrow to the seller.
fillBestOrder selects the cheapest eligible order, breaking ties by creation ID,
and respects the buyer's maximum price. BUY limit orders are not enabled.

The off-chain earlier matching book is retained for historical reads. Creating
new unreserved legacy matches is rejected, since it cannot safely represent the
atomic dual-token settlement model. A confirmed OrderFilled plus both exact
ERC-20 Transfer events creates a unique settlement_obligations record marked
CONFIRMED_SIMULATED. There is no claim that a real peso or dollar was paid.

## Allocation, retirement and audit

A community row lock serializes allocation reservations. Each reservation checks
confirmed source issuance, the consumer's ownership, same-community/time policy,
available injection, verified import and unreserved SUN holdings. Database unique
keys enforce idempotency and one retirement request per allocation. Reservations
remain locked on unknown/failing outcomes until explicit reconciliation; they are
never released merely because an RPC timed out.

A backend authority authorizes a retirement ID, consumer, amount and allocation
hash. The consumer must separately approve a SUN allowance and call retire from
that wallet. An operator cannot burn on the consumer's behalf. Confirmation
requires canonical block depth, CreditRetired with the exact request and evidence,
and the corresponding SUN Transfer-to-zero event. Failed burns never compensate
consumption. Actual ERC-20 burning reduces total supply.

The community ledger is append-only under a PostgreSQL mutation-rejection trigger.
A database administrator still controls the database; this is not a claim of
inherent database immutability. Contract commitments provide external evidence.
Corrections require explicit reversal entries. Canonical-history audits flag
reorganized issuance, payments and retirement for reconciliation and append
reorganization entries instead of editing historical ledger rows.

## Operational boundaries

The local prototype uses a dedicated authority signer, PostgreSQL advisory locks,
unique chain/sender/nonce coordination, and signed raw transactions committed
before broadcast. Retrying a timeout rebroadcasts identical bytes, not a fresh
mint. Failed RPC operations back off and eventually enter DEAD_LETTER. Confirmation
waiting does not count as an RPC failure. Reorganization recovery freezes affected
records for review; it does not automatically invent compensating transactions.
Operators can explicitly request a fee-bumped transaction replacement through
the community operation endpoint. It keeps the nonce, value and calldata fixed,
persists both signed attempts and reconciles whichever receipt becomes canonical.
An operator reconciliation UI and automatic financial reversals are not implemented. Use a dedicated signer and retain the database with the chain;
never reset one side and assume the other side can safely reuse its nonces.

The entire system is a local academic prototype. Public-network rollout needs
independent contract security review, broker TLS/ACL administration, signer key
management, monitoring, and applicable Colombian energy/financial regulatory
assessment. No CREG, UPME or operator rule has been silently encoded as law.
