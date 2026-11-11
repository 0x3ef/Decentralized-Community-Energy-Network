# Blockchain protocol

The current deployment is SUN plus native Anvil ETH (31337/1337) or Sepolia ETH
(11155111). Test ETH has no real monetary value. No payment ERC-20, exchange rate,
or fiat redemption is part of this protocol. Historical ERC-20 contracts, ABIs,
records and tests remain for interpreting earlier deployments; they are not
compatible with this deployment. Do not run the old DeployCommunity script for
a new governed community or relabel historical payments as ETH.

## Authority and physical eligibility

CommunityRegistry owns the boundary/policy commitments, interval length,
lifecycle, operator appointment, membership, nodes and meters. Proposals confer
no operational role. The sequence is PROPOSED → UNDER_REVIEW → APPROVED → ACTIVE;
governance can reject, suspend, resume or archive through permitted transitions.
A positive fixed wei/kWh price must be configured while APPROVED. Changing the
price after activation requires a new reviewed policy/community deployment.
This prototype price is not an electricity tariff.

Admin, registrar and pauser begin at an OpenZeppelin TimelockController with
explicit proposer/executor accounts and no bootstrap externally owned account
(EOA) admin. Public deployment enforces a 24-hour minimum delay; the local fixture
uses zero delay. Choose reviewed organizational or multisig authorities before
shared operation. The timelock is self-administered. Meter registrars,
oracles and settlement authorities must be granted deliberately. Operators do
not gain these roles from their community appointment. Emergency pauser can
be delegated separately. Global pause and community suspension prevent issuance,
deposits, reservations, execution and retirement; owned unreserved funds, SUN
escrow and producer earnings remain withdrawable. Reserved allocations may be
cancelled by their consumer on suspension, or after seven days.

Register members through PENDING → APPROVED → ACTIVE, then physical nodes and
node-bound meters. Wallet verification alone does not establish membership.
Raw telemetry remains off-chain. Ingestion and interval processing require
current community/member/meter authorization and device credentials. Minting
directly from telemetry and legacy outbox issuance are disabled for governed
communities. Existing database communities migrate to UNDER_REVIEW, not ACTIVE.

## Accounting, funding, delivery and retirement

1. A verifier validates physical injection and consumption, aligns UTC intervals
   (default 900 seconds), and applies the committed policy. `allocation.allocate`
   provides integer Wh proportional allocation with largest-remainder rounding,
   deterministic node-ID ties and total bounded by injection and demand.
2. An authorized oracle submits a batch with injection, consumption, allocation,
   price snapshot, interval, policy and a Merkle allocation commitment. Submission
   is CHALLENGEABLE, never final. After the challenge delay, governance explicitly
   finalizes or rejects it. Anyone can inspect evidence; rejection is governed,
   not an automatic fraud-proof system. One canonical finalized batch is allowed
   per community/interval. Superseding requires an unused batch, no issued or
   retired credits and no outstanding or executed financial allocation. Corrections
   after use require explicit external review and a new auditable policy action;
   this prototype has no automatic reversal of paid entitlements.
3. Issuance proof claims mint 1 SUN (18 decimals) per eligible kWh: one integer Wh
   is 10^15 SUN base units. Claims are unique and aggregate issuance cannot exceed
   approved injection. The mint event links the batch, node, meter and beneficiary.
4. Producers explicitly approve and deposit SUN in NativeSettlementVault. Consumers
   explicitly deposit native ETH with a maximum approved wei/kWh price. ETH cannot
   be pulled from an EOA. Governance-approved fixed prices are snapshotted in batches.
5. Settlement authority reserves a proven allocation, simultaneously reserving
   consumer ETH and producer SUN. Cost is ceil(Wh × wei/kWh / 1000). Insufficient
   ETH, price authorization or SUN reverts the whole reservation: the uncovered
   consumption is eligible but UNFUNDED, never paid. Split allocations may be
   committed explicitly; the contract does not silently reduce a claim's quantity.
6. Anyone may execute a funded reservation while participants/community remain
   active. It atomically transfers reserved SUN and credits producer pull-payment
   earnings. No second claim or repeated delivery is permitted. Liability sums
   remain unchanged until withdrawals. Available + reserved + earnings are fully
   backed by vault ETH; available + reserved SUN are backed by escrow SUN.
7. Consumers explicitly approve settlement burn allowance and claim retirement
   with their node/meter consumption proof. Retirement requires the complete
   committed node allocation to have been financially delivered. It burns SUN,
   records community/node/interval uniqueness and makes **no ETH payment**.

Each community deployment has a separate SUN token and immutable community-bound
settlement/vault. Transferable SUN loses individual token provenance; the issuance,
allocation and retirement ledgers preserve evidence instead. Incoming SUN alone
never creates compensation eligibility: an approved member/node/meter, finalized
consumption proof and funded delivered allocation are all required. Escrow SUN
cannot be sold elsewhere. The old USDx marketplace is excluded from this protocol;
there is no new P2P market or BUY-order implementation.

Financial amounts and events can be derived per allocation from the committed
quantity and snapshotted price. The batch is not an assertion that funds already
exist. Actual liabilities/earnings and reserved/settled status are held by the
vault, not inferred from aggregate energy totals.

## Contracts and ABI ownership

| Contract | Active responsibility |
| --- | --- |
| `TimelockController` | OpenZeppelin schedule/execute delay and authorized governance roles |
| `CommunityRegistry` | Community lifecycle, immutable active price, membership, node/meter and protocol bindings |
| `SUNToken` | 18-decimal ERC-20 energy credit, restricted minting, pausing, burn allowance and accounting anchors |
| `CommunitySettlement` | Community-bound evidence batches, challenge/finalization, proven bounded issuance and retirement |
| `NativeSettlementVault` | Consumer ETH deposits, producer SUN escrow, proven reservations, atomic delivery and pull-payment earnings |

The registry exposes `REGISTRAR_ROLE`, `METER_REGISTRAR_ROLE`, `ORACLE_ROLE`,
`SETTLEMENT_ROLE` and `PAUSER_ROLE`. Community operator appointment grants none of
these automatically. The initial SUN `MINTER_ROLE` belongs to the timelock;
commissioning grants it to CommunitySettlement and revokes that bootstrap grant.
The dedicated backend signer receives only oracle/settlement authority in the demo.

Canonical Solidity is in [contracts/src](../contracts/src); compiler artifacts live
in ignored `contracts/out`. [scripts/sync_abis.py](../scripts/sync_abis.py) checks
the five native protocol ABIs shared by backend and frontend. Use `--write` only
after reviewing intentional contract changes. Legacy marketplace, MockUSD and
redemption contracts/ABIs remain for historical tests; they are not a native ETH
P2P market or an active fiat payout system. `RedemptionManager` is distinct from
consumption-credit retirement and must not be substituted for it.

## Deployment and participant calls

[Getting started](getting-started.md) owns local bootstrap commands;
[deployment](deployment.md#sepolia-deployment-and-commissioning) owns the public
preflight/broadcast procedure. Do not use old `DeployCommunity` instructions for a
governed native community. No public contract addresses are documented because no
public deployment has been verified. Local deployment metadata is in ignored
`.run/demo/demo.json` and receipt journals; it is invalid after an independent
chain reset.

Participants sign their own `deposit`, `depositSUN`, `withdraw`, `withdrawSUN`,
`withdrawEarnings` and `retire` interactions. ERC-20 approval for SUN escrow targets
the vault; approval for retirement targets CommunitySettlement. ETH deposits use
native transaction value and a maximum approved wei/kWh price, not ERC-20 allowance.
The API's native preparation endpoint returns unsigned calldata and expected chain,
target and value; it does not move funds. Governance finalization is a separate
authorized contract call, currently outside the API's registry preparation actions.

Wallet ETH, available vault ETH, reserved ETH, claimable earnings, escrow SUN and
reserved SUN are different balances. `escrow_sun_units` in native wallet responses
is already the **available** escrow amount. The frontend must not subtract reserved
SUN again. SUN transfers change ownership but do not themselves establish eligible
consumption or compensate an electricity bill.

## Reconciliation

[CommunityChain](../apps/backend/src/modules/community/chain.py) coordinates signed
operations; [NativeSettlementChain](../apps/backend/src/modules/settlement/chain.py)
submits and indexes native work. Before broadcast, raw signed bytes, hash, nonce and
origin are committed to `community_chain_operations`. Current nonce uniqueness is
chain ID + genesis hash + sender + nonce. Pending signatures with unknown/mismatched
origin are BLOCKED/FAILED; they require explicit receipt review. Never assign an
origin by guess or automatically sign another payment.

A successful submitted hash is insufficient. Receipt status, canonical block hash,
confirmation threshold, expected contract/events and confirmed index updates must
agree. The backend defaults to two confirmations; the UI waits for at least one
local or three Sepolia confirmations, then waits for backend confirmation/indexing.
Thus the UI's local receipt gate does not lower the backend's policy.

Workers audit stored receipts and cursor history, retain orphaned events with
`canonical=false`, and rebuild affected projections from confirmed contract state.
A testable Anvil reorganization is covered by integration tests. Missing bytecode
marks native batches and previously confirmed participant projections
RECONCILIATION_REQUIRED. This is quarantine, not restoration of a lost chain.
There is no automatic reversal of already-paid entitlements.

Explicit operator fee replacement preserves nonce/value/calldata and signed attempt
history. An ambiguous RPC result reuses the journaled operation, not a new mint.
Terminal reverted work requires explicit retry after reviewing funding/authority.
User transactions always require the user's own signature. The browser retains
hashes scoped by user/community/wallet/chain, but its journal is neither a canonical
ledger nor cross-device transaction history.

## Local and public verification limits

Supported governed networks are Anvil 31337/1337 and Sepolia 11155111; the default
Docker node is 31337. Sepolia tooling is implemented, but RPC/funding/authority
configuration and actual public acceptance execution remain outstanding. Simulated
source evidence is eligible only in an opted-in local community. Public-chain
source verification, real meter calibration and independent contract audits are
not established by local tests. See [verification](verification.md) and
[security](../SECURITY.md).
