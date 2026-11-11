# Development and maintenance

Install and start the local environment using [getting started](getting-started.md).
Keep application, oracle, participant and governance identities distinct. There is
no prescribed commit-message policy or official contribution workflow beyond the
repository's executable checks; review expectations below follow its actual code.

## Executable checks

Activate the installed Python environment. Host contract commands use
`.dev-tools/node_modules/.bin/forge` and `.dev-tools/solc-0.8.24`; pass `DEV_TOOLS`
when using a different tool directory.

```bash
make test
make test-contracts
make test-backend
make test-iot
make test-frontend
python scripts/sync_abis.py
```

`make test` invokes all four suites. Backend tests run on the **host virtual
environment**, not inside a test container. Their script starts disposable test
services, creates a uniquely named PostgreSQL database, applies all migrations,
runs pytest and drops only that database on exit. Ports are PostgreSQL 55432,
MQTT 18884, Redis 16379 and Anvil 18545. Do not substitute development endpoints.
Test Compose commands explicitly select `solar-prototype-tests`, overriding any
private development COMPOSE_PROJECT_NAME so tests cannot recreate the app node.
The IoT test script starts its own gateway and uses the isolated broker; its
coverage gate is 80%.

Frontend checks run strict TypeScript, oxlint, Vitest and a Vite production build.
Python tools are Ruff check/format, configured in project files; `make lint` and
`make format` target backend/IoT. `make typecheck` invokes mypy but the backend
extra does not itself install mypy; the IoT development extra does. Existence of
a target is not a claim that its complete current tree is clean.

The [CI workflow](../.github/workflows/verify.yml) installs dependencies, executes
these suites, bootstraps the Docker demo, replays the financial scenario after
worker restart and runs real-API browser tests. A configured workflow is not
proof that a particular GitHub Actions run succeeded.

## Browser fixtures

Keep the development API/Anvil stack running, compile contract artifacts, and run
`make demo` plus `make demo-scenario` first to enable both production balance checks.
Start Vite in one terminal:

```bash
cd apps/frontend
npm run dev -- --host 127.0.0.1
```

In another terminal, with Python/Docker available:

```bash
cd apps/frontend
npm run test:e2e:all
```

Playwright uses system `/usr/bin/chromium` when present; otherwise install its browser
with `npx playwright install --with-deps chromium`, or set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE`. The native seed requires compiled artifacts and
the canonical API container. It temporarily stops the worker, deploys isolated
contracts/users, feeds authenticated evidence through backend services, then
restarts the worker. Do not run it concurrently with bootstrap or another native
fixture. Every complete run needs a fresh fixture because retirement and membership
changes mutate chain state.

The ignored `apps/frontend/e2e/.native-fixture.json` contains local bearer tokens.
The seed updates only public chain/registry/timelock fallbacks in `.env.local`.
Those may differ from the root demo deployment afterwards; rerun `make demo` to
restore the demo fallbacks when needed. The two production checks use the Docker
frontend and actual balances from the finite MQTT scenario; they skip if its runtime
artifacts are absent. Test EIP-1193 transport forwards actual RPC to impersonated
Anvil accounts. No actual MetaMask extension or public Sepolia acceptance is implied.

## Frontend conventions and financial safety

`src/app` owns sessions, routing and responsive shell; `src/features` owns domain
screens; `src/shared/api` owns typed cancellation-aware adapters, bearer refresh,
user-scoped queries and Spanish errors. `src/shared/blockchain` owns wallet listeners,
ownership/role proofs, ABI validation and transaction recovery. The UI is Spanish;
this documentation is English. Theme persists locally; bearer tokens use
`sessionStorage`, separate from transaction history.

Money remains decimal integer strings/BigInt through parsing, formatting and signing.
Tiny positive values must not round to zero; unavailable balances remain visibly
unknown. Chart coordinates may use Number. Native wallet ETH, vault ETH, reserves,
earnings and SUN escrow have distinct meanings. See [blockchain](blockchain.md).

Transactions move through preparation, signature, submission, confirmation or
failure/reconciliation states. Review includes chain, sender, destination, exact
value and calldata. Account/network/community are rechecked before send. Governance
calls are simulated; allowance approvals use exact amounts and correct spenders.
The UI waits for backend confirmation/indexing and never fabricates optimistic
balances. Delays preserve transaction hashes for recovery. Timelock schedule and
execute are separate signatures, and external proposals are not automatically
imported across browsers.

Lists remain bounded: paginated settlement/transaction/claim selectors, operator
jobs up to 50, latest telemetry 5, and 24h/7d/30d energy ranges. The dashboard labels
its selected home, rolling day and last-five-batch history; these are not lifetime
personal totals. Full participant manifests and SUN event histories remain gaps.

Retained local screenshots: [desktop](../apps/frontend/docs/screenshots/dashboard-desktop.png),
[mobile](../apps/frontend/docs/screenshots/dashboard-mobile.png),
[dark](../apps/frontend/docs/screenshots/dashboard-dark.png), and
[financial workspace](../apps/frontend/docs/screenshots/deposits-desktop.png).
They are fixture-based historical visual evidence, not public-network execution.

## Schema and generated artifacts

SQLModel/Alembic own schema; use the [database workflow](database.md#migration-and-recovery-workflow).
Review migrations against fresh and populated databases, including financial-history
preservation. Do not change historical asset units or erase failed transaction attempts.

When contracts change, compile/test them, inspect intentional ABI changes and run
`python scripts/sync_abis.py --write`, then check again without `--write`. This
updates canonical native backend/frontend ABIs together. Old payment-token ABIs
remain distinguishable.

When API schemas change, refresh `apps/frontend/scripts/openapi.json` from the live
`/api/v1/openapi.json`, run `npm run generate:api` in `apps/frontend`, and update
explicit models for untyped endpoints. Then typecheck/test the API adapter.
Generated gRPC modules live in `iot/grpc_client`; editing `iot/protos/sensor.proto`
requires regeneration with the `protos` target in `iot/Makefile`. That Makefile's
older stack commands are not the canonical governed setup.

## Documentation maintenance

Plain English Markdown under `docs` is authoritative, indexed once in the root
README. Avoid adding another setup guide, module README or historical status report
that competes with these sources. Keep evidence clearly dated/scoped and retain
public artifacts without credentials.

| Change | Documentation and checks to update |
| --- | --- |
| API | `api.md`, live OpenAPI snapshot, generated/adapted frontend types and schema examples |
| SQLModel or migration | `database.md`, migration head/constraints and relationship diagram |
| Contract/roles/network | `blockchain.md`, deployment procedure, ABI synchronization and trust assumptions |
| Telemetry/commissioning | `iot.md`, versioned example validation, units, source/mode and credential rules |
| Allocation/price/correction policy | `community-settlement.md`, worked exact-wei example and evidence limits |
| Runtime setting | `configuration.md`, matching relevant `.env.example` and actual Compose precedence |
| Setup/test automation | `getting-started.md` or this guide; execute safe checks before claiming success |

Check relative links and anchors, fenced examples against their Pydantic schemas,
route paths against current OpenAPI, model/table names against metadata and config
names/defaults against Settings. Run a Markdown linter when available and
`git diff --check`. Avoid rerunning destructive bootstrap or public broadcasts just
to validate documentation. New verification claims must name what actually ran.
