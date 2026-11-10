# Solar Energy Market · frontend

Spanish-first community energy application built with React, strict TypeScript,
Vite, Tailwind CSS, TanStack Query, viem, Recharts and Lucide. All application
screens use the actual FastAPI API. No sample balances or telemetry ship in the app.

```bash
cd apps/frontend
npm ci
cp .env.example .env.local  # choose the chain and public deployment settings
npm run dev -- --host 127.0.0.1
npm run typecheck
npm run lint
npm test
npm run build
```

Start the backend using the repository's existing development-stack instructions.
Vite proxies `/api` to `127.0.0.1:8000`; the prototype nginx already provides the
production `/api` proxy. `VITE_API_URL` includes `/api/v1` for an external API.
Vite variables are public build-time configuration, never wallet keys or secrets.
Only native Anvil/Sepolia ETH settlement is active. Sepolia ETH has no monetary
value. There is no fiat conversion or native-ETH marketplace in these contracts.

## Architecture

- `src/app`: protected session gate, providers, lazy routes, responsive shell,
  community selection, keyboard navigation and persistent light/dark preference.
- `src/features`: authentication, communities, homes, devices/quality/energy,
  SUN credits, settlement, deposits/withdrawals, retirement and governance.
- `src/shared/api`: cancellation-aware typed adapter, single-flight bearer refresh,
  Spanish error normalization, user-scoped cache and polling hooks.
- `src/shared/blockchain`: EIP-1193 connection, account/network listeners, ownership
  challenge, role proof, allowance reads, ABI validation and transaction controller.
- `src/shared/ui`: cards, feedback, forms, focus-managed native dialogs and error
  boundary. Spanish navigation/status vocabulary lives in `i18n.ts`; other copy
  remains Spanish. A second full translation is not bundled.
- `scripts/openapi.json`: audited FastAPI snapshot. `npm run generate:api` regenerates
  `src/shared/api/generated.ts`. Untyped JSON endpoints have explicit adapter models.
  ABIs are copied from the canonical backend artifacts; refresh them together when
  contracts change.

Login/signup/refresh/logout use FastAPI bearer tokens. Tokens live in sessionStorage,
not the persistent transaction journal. The backend has no HTTP-only cookie flow.
Application authentication and wallet ownership are separate. Wallet linking signs
an EIP-191 challenge; connecting alone grants no protocol permissions. The app never
asks for private keys. Governance navigation requires roles read from the selected
registry and configured timelock; every privileged request is enforced again by the
backend and contracts. An operator is distinct from a governance registrar.

Financial quantities stay decimal integer strings/BigInt through validation,
formatting and signing. Only energy chart coordinates use Number. A positive tiny
balance displays a lower-bound marker instead of zero; unavailable values display
`—`. Native wallet ETH, available vault ETH, reserved ETH, producer earnings,
withdrawn earnings, available escrow SUN and reserved SUN are separate balances.
`escrow_sun_units` is already the vault's **available** SUN; reserved SUN must not
be subtracted from it a second time. SUN uses 18 decimals, 1 SUN per eligible kWh,
and retirement calls take integer Wh. Household load is never inferred from signed
net grid power. Sensor cards label stale readings, source and physical authorization.

## Signing and recovery

Transactions move through IDLE, PREPARING, AWAITING_SIGNATURE, SUBMITTED, CONFIRMING,
CONFIRMED, FAILED and RECONCILIATION_REQUIRED. Preparation validates network, sender,
contract, selector, exact amount, recipient, allowance spender and retirement proof.
Governance calls are simulated before review. The review shows native value, chain,
destination and calldata. Account/network/community are checked again before send.

The UI requires one Anvil or three Sepolia receipt confirmations, then waits for the
backend's own confirmation/indexing policy. It never optimistically increments a
balance. Repriced transactions retain the replacement hash; cancellations or
substantive replacements do not confirm the original action. Delays preserve the
hash and offer receipt/reconciliation controls in Transacciones. Journals are scoped
by user, community, address and chain and survive reloads on this browser. They are
not a canonical ledger or a cross-device history. Non-native governance records use
receipt verification without calling the native transaction endpoint. Transition
synchronization can be retried after reloading.

SUN approvals use exact entered amounts. Deposit and retirement approvals target
different contracts. Consumption can retire SUN only from a finalized batch whose
own claim is delivered and explicitly retirement-eligible. This creates no second
ETH payment and makes no promise about an official electricity bill. Price changes
are limited to the contract's APPROVED community state. Timelock scheduling and
execution are separate signatures; execution reads readiness from the contract.

## Browser verification

A real API and Vite server must be running. Chromium defaults to `/usr/bin/chromium`;
override `PLAYWRIGHT_CHROMIUM_EXECUTABLE` for another machine.

```bash
npm run test:e2e -- e2e/community.spec.ts e2e/wallet-link.spec.ts
# Local Anvil/PostgreSQL contracts and SQLModel fixture, followed by wallet journeys:
npm run test:e2e:native
# Or create a fresh fixture and run all browser journeys together:
npm run test:e2e:all
```

The native fixture requires the existing Docker Compose development API/Anvil stack,
compiled Foundry artifacts in `contracts/out`, Python 3 and Docker. It refuses other
chains/environments. It creates isolated users, random impersonated/funded **test**
wallets, a governed registry/timelock, authorized simulated meters, authenticated
telemetry, finalized issuance, funded allocation and delivered consumption using real
contracts and backend services. It temporarily stops the development worker while
seeding to avoid racing its cursor/nonce writes, then starts it again. It does not
change backend, contract or infrastructure source files. Test wallet transport exists
only in `e2e/native.spec.ts`; it forwards RPC requests to local Anvil. The MetaMask
extension itself and a live Sepolia network are not part of these automated tests.

Run the seed before **each complete native suite**: retirement and membership actions
are stateful and irreversible on that test deployment. The ignored
`e2e/.native-fixture.json` contains local test bearer tokens. The fixture updates only
public registry/timelock/chain settings in `.env.local`; these addresses are not
portable to Sepolia or a restarted Anvil instance. Do not commit fixture credentials.
In a managed proxy environment, both `NO_PROXY` and `no_proxy` inside API/worker must
include the internal service hostnames (anvil, timescaledb, redis, mosquitto), alongside
localhost. Keep external proxy/TLS settings intact.

## Backend integration boundaries

The UI explicitly reports these missing capabilities instead of inventing endpoints:

- A global community directory, complete membership application directory and profile
  editing. Community list returns active memberships and the user's own proposals;
  another community can be joined using its known UUID.
- Full participant-visible batch evidence manifests and a complete issuance-hash join
  from every native credit to a transaction. Own claims expose nodes, meters, interval
  batch and Merkle proofs; an operator can inspect batch jobs and chain hashes.
- Complete SUN transfer/retirement event history and historical vault movements by
  amount. Credit accounting, current balances and available transaction records are
  shown separately; no token-by-token origin is asserted for fungible SUN.
- Discovery/import of timelock proposals scheduled on another device and direct batch
  finalization preparation via the API. Local prepared registry operations support
  schedule/execute; protocol batch finalization remains an external governance task.
- Native ETH P2P trading, AMMs and utility billing integration.

Lists with paginated API support expose pagination for settlement and transaction
history, evidence and compensation selectors, with 20 records per page; operator
jobs currently show up to 50 and telemetry the latest 5 records. Energy ranges offer 24h,
7d and 30d. The dashboard explicitly labels the selected home, rolling 24-hour period
and last-five-lot community history, rather than presenting partial totals as lifetime
personal accounts. See `VERIFICATION.md` for executed checks and practical limits.

[Desktop preview](docs/screenshots/dashboard-desktop.png) ·
[Mobile preview](docs/screenshots/dashboard-mobile.png) ·
[Dark theme](docs/screenshots/dashboard-dark.png) ·
[Financial workspace](docs/screenshots/deposits-desktop.png)
