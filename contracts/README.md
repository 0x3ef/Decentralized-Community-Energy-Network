# Contracts — Solar Energy Market

Foundry project with three contracts:

| Contract | Purpose |
|---|---|
| `SUNToken` | ERC-20 token. 1 SUN = 1 kWh of eligible export energy. Minted by the backend when a credit is approved. |
| `EnergyMarketplace` | Order-book marketplace for SUN tokens. Sell orders are placed on-chain; the backend calls `fillOrder` after matching. |
| `RedemptionManager` | Burns SUN and pays the redeemer in native ETH at a configurable rate. |

## Setup

```bash
# Install Foundry (if not installed)
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Install dependencies
forge install foundry-rs/forge-std --no-git
forge install OpenZeppelin/openzeppelin-contracts --no-git

# Build and test
forge build
forge test -vvv