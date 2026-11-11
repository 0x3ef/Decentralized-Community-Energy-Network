# Governed community protocol (current)

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

Admin, registrar and pauser begin at an OpenZeppelin TimelockController with a
24-hour minimum delay and no bootstrap EOA admin. Its proposer/executor is the
explicit deployment signer; transfer those roles to reviewed multisig accounts
before shared operation. The timelock is self-administered. Meter registrars,
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

## Deployment and interactions

Compile and test before deployment:

```sh
forge test --root contracts
# Set COMMUNITY_ID to a nonzero bytes32 community identifier.
# Provide BACKEND_PRIVATE_KEY via the environment/secret store, never source code.
forge script contracts/script/DeployGoverned.s.sol:DeployGoverned \
  --root contracts --rpc-url "$WEB3_PROVIDER_URL" --broadcast
```

The script accepts only Anvil or Sepolia, deploys registry, timelock, SUN,
settlement and native vault, prints addresses, and activates nothing. Save chain
ID and these addresses from Foundry broadcast receipts. Schedule then execute
through the timelock: SUN.grantRole(MINTER_ROLE, settlement), revoke the timelock's
SUN mint role, settlement.bindVault(vault), registry.bindProtocol(community, settlement, vault, SUN),
registry oracle/settlement role grants,
community lifecycle, fixed price, membership, nodes and meters. The timelock delay
must elapse before execute. Recheck roles and bindings before using deposits.
No public Sepolia deployment is implied by local tests.

Set WEB3_PROVIDER_URL, CHAIN_ID and COMMUNITY_REGISTRY_ADDRESS for the selected
chain; do not reuse local addresses on Sepolia. New native deployments are stored
separately from historical ERC-20 deployments. The API checks chain ID and mutual
contract/registry/SUN bindings and governance-approved protocol addresses before registration.
Operators cannot substitute an arbitrary vault. The browser switches to the
registered chain, signs with the user's verified wallet, awaits receipt confirmation
and retains submitted hashes when reconciliation is required.

Authenticated API under `/api/v1/communities`:

- POST `/` creates a DRAFT with proposer PENDING membership, no operator.
- POST `/{id}/propose` commits physical boundary/policy and returns unsigned calldata.
- POST `/{id}/governance/sync` with transaction_hash verifies a canonical registry
  transition receipt and current chain state before synchronizing authority.
- POST `/nodes/{id}/governance/sync` verifies the registered node owner.
- POST `/{id}/native-deployment` registers chain_id, sun_address,
  settlement_address and vault_address after governance activation.
- GET `/{id}/native-wallet` reads actual chain balances, escrow and earnings.
- POST `/{id}/native/prepare` simulates and prepares unsigned wallet calldata for
  deposit, withdraw, withdraw_earnings, approve_sun, escrow_sun, withdraw_sun,
  approve_retirement, execute and retire. All amounts are decimal integer strings
  in base units; retirement amount is integer Wh. Preparation never submits a
  transaction or records a payment as confirmed.

The [automated backend pipeline](AUTOMATED_SETTLEMENT.md) now prepares proofs,
submits batches, indexes confirmations and executes funded allocations. Governance
finalization and user wallet actions remain explicit. Use `leaf` on settlement/vault to construct leaves:
kind 0 issuance, 1 retirement, 2 financial allocation; each is double-keccak ABI
encoding, with sorted-pair Merkle branches. Claim/batch IDs and proof nodes are
bytes32. Use the final ABI JSON files in backend blockchain/abis, not legacy ABIs.
The Foundry Governance.t.sol fixture is an executable interaction example.

## Trust and limitations

The oracle and governance must verify measurement truth, producer allocation
eligibility, policy interpretation and the correctness of committed individual
caps. Merkle proofs establish commitment membership, not physical truth. The
contract independently enforces roles, lifecycle, interval uniqueness, aggregate
bounds, funding, node ownership, replay protection and conservation. A compromised
governance majority can assign malicious future authorities. Preserve immutable
evidence and monitor role and batch events. There is no proxy upgrade mechanism.
Reentrancy guards and reverting external transfer failures preserve balances;
there is no operator sweep. Forced ETH is surplus, not a member liability.

This is a tested prototype, not independently audited production infrastructure.
