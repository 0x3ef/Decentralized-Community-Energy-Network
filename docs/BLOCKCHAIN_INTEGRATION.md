# Blockchain integration

The blockchain layer is an EVM settlement boundary. PostgreSQL remains the
system of record for telemetry, approvals, orders, and reconciliation
metadata; the chain stores token balances and settlement events.

## Contracts

| Contract | Responsibility | Owner |
|---|---|---|
| `SUNToken` | 18-decimal SUN token; minting is restricted to `owner` | Backend deployer account |
| `EnergyMarketplace` | Escrows SUN sell orders and settles native-coin payment | Public order placement/fill; maker cancellation |
| `RedemptionManager` | Escrows native coin, transfers SUN to a burn sink, and pays redeemers | Backend owner configures rate/funding |

One SUN represents one kWh of eligible export energy. Contract amounts are
integer token units (`1 SUN = 10^18`), while the backend accepts `Decimal`
whole-token amounts and converts them in `TokenService`.

## Deployment

`contracts/script/Deploy.s.sol` deploys all three contracts using
`PRIVATE_KEY`, writes `contracts/deployments/<chain-id>.json`, and preserves
the same deployer as the contract owner. The local setup scripts export
`PRIVATE_KEY` from `BACKEND_PRIVATE_KEY` when necessary, so the backend signer
can mint SUN and execute owner operations.

```bash
make setup
# or, with Anvil already running:
make contracts-deploy
```

Addresses are injected into `infrastructure/docker/.env` as
`SUN_TOKEN_ADDRESS`, `ENERGY_MARKET_ADDRESS`, and
`REDEMPTION_MANAGER_ADDRESS`. Never commit a private key or deployment
environment file.

## Backend transaction lifecycle

`Web3Client` lazily connects to the configured RPC, derives the signer, reads
the chain id, estimates gas, signs, broadcasts, and waits for a receipt.
`TokenService` is the high-level mint/transfer boundary. A successful
submission is not a successful settlement: callers must require receipt
status `1`, record the transaction hash and block, and reconcile emitted
events.

The database has `blockchain_transactions` and `blockchain_events` for this
purpose. Use an idempotency key for every business operation; retries must
reuse the key and must not mint or settle twice. Reverted receipts remain
visible as failed work for reconciliation.

## Flows

### Credit issuance

1. Telemetry is validated and aggregated off-chain.
2. An approved interval creates an `energy_credits` row.
3. The worker calls `SUNToken.mint(wallet, amount * 10^18)`.
4. The receipt and `Transfer(address(0), wallet, amount)` event are recorded.
5. The credit becomes `issued` only after successful confirmation.

### Marketplace settlement

Sell orders escrow SUN in `EnergyMarketplace`. A buyer fills an order with
native coin; the contract transfers SUN to the buyer, pays the maker, refunds
overpayment, and emits `OrderFilled`. The off-chain order/trade status must
not be marked confirmed until that event is reconciled.

### Redemption

The owner funds `RedemptionManager` and sets `weiPerToken`. A user approves
the manager, calls `redeem`, and receives native coin after SUN is transferred
to the `0xdead` sink. The contract must remain funded; withdrawals reduce
available redemption liquidity.

## Verification

```bash
cd contracts
forge test
forge build
cast call "$SUN_TOKEN_ADDRESS" "owner()(address)" --rpc-url http://127.0.0.1:8545
```

The API endpoint `/api/v1/blockchain/status` checks RPC connectivity and
chain id. `/api/v1/blockchain/transactions/{tx_hash}` exposes local
reconciliation state without exposing signer material.
