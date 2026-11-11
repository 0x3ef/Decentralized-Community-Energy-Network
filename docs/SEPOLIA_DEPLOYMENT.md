# Sepolia deployment and commissioning

This is an explicit public-testnet procedure, not a claim that deployment occurred.
The local demo's automatic authority and impersonated accounts are prohibited here.

## Secure configuration and preflight

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

## Community and protocol commissioning

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
   Simulated sources must be explicitly allowed and visibly labeled.
7. Have each user connect/verify their own wallet, deposit native ETH or approve and
   escrow SUN as needed. The server never signs participant payments or withdrawals.
8. Review an evidence commitment; finalize eligible batches through authorized
   governance after the challenge period. Automatic backend processing may then
   reserve/deliver funded allocations. Finalization is not delegated to an ordinary
   operator. Retirement requires delivered, finalized consumption and SUN allowance.

## Run the stack against Sepolia

Set `COMMUNITY_REGISTRY_ADDRESS`, `GOVERNANCE_TIMELOCK_ADDRESS`, and
`NATIVE_SETTLEMENT_START_BLOCK` (the earliest confirmed deployment block from the
journal). Configure JWT/database/MQTT settings appropriately. The public browser RPC
`VITE_SEPOLIA_RPC_URL` is optional and must not contain a private provider credential.

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
