# Frontend rebuild verification

Executed in the managed development environment on 2026-11-10, against the
existing FastAPI/PostgreSQL/Redis/Anvil stack. Changes are confined to
`apps/frontend`; backend, contract and infrastructure source files are unchanged.
The cloud environment was not published.

| Check | Result |
| --- | --- |
| Strict TypeScript | `npm run typecheck` passed |
| Oxlint | `npm run lint` passed without warnings |
| Vitest | 35 tests passed across 6 files |
| Production bundle | `npm run build` passed; route/chart code split |
| Playwright, API and native suite | 8 tests passed in one complete run |
| Playwright, ownership/membership | 1 additional test passed |
| Read-only browser route inspection | All 12 top-level routes rendered without page errors |
| Responsive visual checks | Desktop 1440px, mobile 390px, light/dark; no horizontal overflow |

Unit/component/hook tests cover exact large integer amounts, tiny balances,
missing-versus-zero values, decimal validation, request cancellation, concurrent
refresh, rejected refresh, public-request token isolation, forbidden API responses,
retry feedback, device empty-list normalization, wallet accounts/listeners,
explicit connection, Sepolia chain switching, transaction states and prepared-call
validation (wrong destination, allowance, amount and withdrawal recipient).

Browser journeys exercised:

1. Protected routes, signup, login, failure feedback, session recovery and logout.
2. Community proposal, home creation, pending device creation with MQTT identity,
   source/health, empty energy/credits, mobile navigation and theme persistence.
3. Ownership challenge signed by an ephemeral test account and verified by the
   actual backend; a real membership application returns PENDING without granting
   governance privileges.
4. Explicit wallet connection, wrong-network blocking and network switching.
5. Native ETH deposit, review amount, receipt/backend confirmation, insufficient
   available-funds rejection, withdrawal and server transaction history.
6. Authenticated simulated injection, energy intervals, SUN credit/issuance record,
   actual personal allocations, settled obligation and producer earnings withdrawal.
7. Delivered consumption selection, exact SUN approval and confirmed retirement;
   a retired claim becomes unavailable for a second retirement.
8. Escape cancellation and user-rejected signing leave deposited funds unchanged.
9. Proven registrar role, simulated preparation, user signature and confirmed
   membership governance transaction.

The native fixture deploys actual contracts and creates SQLModel records through
backend services. It feeds authenticated simulated meter evidence through the real
energy processor, finalizes a real governed batch, escrows producer SUN and funds
consumer ETH before delivery. No production component uses fixtures or mock data.
The test-only EIP-1193 adapter forwards real RPC reads/transactions to Anvil. The
ownership test signs a real EIP-191 message. No wallet private key enters the app.

A contract rule discovered during testing prohibits price configuration after
activation. The UI now disables that action outside APPROVED and simulates all
prepared governance calls before asking for a signature. Device registration was
also checked against the real API's mandatory MQTT identity, and the documented
404 empty-device response is normalized without hiding missing-home/permission
errors. Native SUN escrow reads already exclude reserves; withdrawal checks use
that available amount directly.

Visual artifacts use the explicit local fixture, after the browser journeys:

- [Desktop dashboard](docs/screenshots/dashboard-desktop.png)
- [Dark dashboard](docs/screenshots/dashboard-dark.png)
- [Mobile dashboard](docs/screenshots/dashboard-mobile.png)
- [Deposit/withdrawal screen](docs/screenshots/deposits-desktop.png)

Practical limits: the actual MetaMask extension and a live Sepolia deployment were
not exercised. Sepolia configuration/network behavior is covered with an injected
wallet test. Repricing/replacement/timeout recovery is implemented, but no live
replacement or chain-reorganization browser scenario was run. A formal WCAG audit
was not performed. Backend/Foundry/IoT suites were not rerun for this frontend-only
change. The API limitations and bounded telemetry/job views are documented in
README.md; missing event histories, public directory, profile editing, cross-device
timelock discovery and native marketplace are not claimed as implemented.
