# Verification record

## Scope and evidence date

The following results were executed in the prior integration work at commit
`e061ab0`, before this documentation-only audit. Test counts are historical evidence,
not a claim that the full application suite was rerun for documentation changes.
Current documentation checks are recorded in [documentation audit](documentation-audit.md).

The canonical path uses native test ETH and SUN. Docker starts reviewed Alembic
migrations before application services. A deterministic, local-only commissioner
creates SQLModel identities and uses real timelock transactions to authorize the
community, policy, participants, nodes and meters. It deploys the five canonical
contracts, isolates the oracle from governance and participants, and revokes the
bootstrap SUN minter. Existing identities and accounting are checked and preserved.

The finite demonstrator exercises authenticated MQTT ingestion, quality checks,
deduplication, interval accounting, automatic allocation, the actual background
worker, confirmed EVM transactions, SUN delivery and retirement, and producer
withdrawal. Continuous REALTIME simulation uses independent meter identities so
it cannot reset the finite fixture's counters.

The API and Spanish frontend expose service readiness and operator reconciliation
status. Native chain operations record the genesis hash as well as chain ID, sender
and nonce. Pending operations from another or unknown chain origin are blocked;
missing deployed code quarantines affected records for reconciliation. A local
chain reset never silently reuses old confirmed financial projections.

## Executed local evidence

[Machine-readable scenario](evidence/local-native-scenario.json) records the actual
MQTT/API/worker/Anvil execution, including the local community, batch, statements
and participant transaction hashes. These are local Anvil receipts, not Sepolia
transactions or explorer-verifiable public deployments.

| Verified quantity | Confirmed result |
| --- | --- |
| Eligible net injection / demand | 5 kWh / 3 kWh |
| Allocation / unallocated injection | 3 kWh / 2 kWh |
| Price | 0.001 Anvil ETH/kWh |
| Consumer deposit / settlement | 0.01 ETH / 0.003 ETH |
| Consumer available / reserved funds | 0.007 ETH / 0 ETH |
| Producer entitlement / earnings withdrawn | 0.003 ETH / 0.003 ETH |
| SUN issued / delivered / retired | 5 / 3 / 3 SUN |
| Remaining SUN supply | 2 SUN |
| Vault liabilities after withdrawal | 0.007 ETH |

The scenario rejected an invalid device credential and replayed valid boundary
packets. Restarting the worker and rerunning the journaled scenario succeeded
without another deposit, settlement, retirement or earnings withdrawal. Bootstrap
was also rerun against the existing deployment and preserved its identities.

An isolated Docker Anvil restart probe using the configured persistent state and
historical-state flags preserved the genesis hash, account nonce and transaction
receipt history. This is a node persistence check; it does not establish recovery
from every infrastructure failure or an arbitrary public-chain reorganization.

## Verification executed in this environment

| Check | Result |
| --- | --- |
| Foundry contract suite | 38 passed |
| Backend integration suite, fresh PostgreSQL migrations and real test services | 48 passed |
| IoT suite, isolated MQTT broker and gateway | 86 passed; 84.62% coverage |
| Frontend unit/component/hook/wallet suite | 35 passed |
| Frontend strict TypeScript, lint and production build | Passed |
| Canonical contract ABI synchronization check | Passed |
| Full browser journeys against real local API and EVM | 11 passed |
| Complete local financial scenario and worker-restart replay | Passed |
| Sepolia preflight without credentials | Correctly stopped before RPC/broadcast, exit 2 |

The browser suite uses an explicit local EIP-1193 wallet transport for transaction
journeys. The production Docker frontend additionally verifies the real producer
and consumer balances from the MQTT scenario and the service-status screen.
This does not claim that an installed MetaMask extension or a public Sepolia flow
was exercised. GitHub Actions is configured to repeat verification; its remote
execution is separate from these locally executed checks.

The contract suite covers unauthorized activation and oracle submission, cross-community
batches, suspended operations and preserved exits, unauthorized meters, insufficient
and partial funding, invalid proofs, repeated issuance/retirement, reserved SUN,
failed withdrawals, reentrancy and fuzzed liability backing. Backend integration
covers receipt/index confirmation, replay/crash recovery, transaction replacement
and a testable Anvil reorganization. The new governed MQTT test additionally checks
actual provisioning, rejected credentials, deduplication, double withdrawal,
retirement replay, and quarantine of an unanchored signed transaction.

Integration testing found and corrected standalone SQLModel relationship
registration, stale nonce handling after a local chain reset, internal proxy
routing, nginx API/static-route precedence, and Docker DNS refresh after API
recreation. A failed local browser artifact exposed a generated demo password;
the credential and all affected encrypted demo keystores were rotated and the
artifact removed. Production balance tests now authenticate through HTTP so that
password does not enter a browser DOM snapshot. No current runtime secrets belong
in the tracked evidence.

## Sepolia status and remaining verification

**No public deployment was executed.** This environment has no configured Sepolia
RPC, funded deployment signer or public governance authority configuration.
Preflight stopped before any broadcast. No public contract addresses, transaction
hashes, faucet funding, source verification or public end-to-end success is claimed.

[Sepolia deployment instructions](deployment.md#sepolia-deployment-and-commissioning) cover secure configuration,
funding checks, authority separation, resumable receipt-confirmed deployment,
three confirmations, the minimum one-day timelock/challenge periods, governance
commissioning and wallet verification. Public deployment still requires these
external inputs and a deliberate broadcast, followed by governance review and
end-to-end verification on that network. Never paste private keys into chat or put
an authenticated RPC URL into frontend configuration.

The anonymous broker and zero-delay governance are loopback-only development
conveniences. Real devices require authenticated broker ACLs/TLS, protected device
provisioning and trustworthy metrology. Oracle trust, timestamp/measurement
integrity and governance authority remain explicit assumptions. No physical energy
routing, utility-bill adjustment, legal authorization, security audit, or
production readiness is implied.

Native ETH P2P trading, public community discovery, profile editing, complete
participant-visible evidence and full SUN event histories remain outside the
current API. Legacy payment-token workers are disabled by default; old artifacts
are retained for compatibility. Reconciliation quarantines stale historical local
communities rather than deleting their users or inventing replacement receipts.

## Earlier verification context retained

Earlier reports described distinct implementation stages, not simultaneous current
results: initial USDx-era verification (20 contract / 9 backend / 44 IoT tests),
governed native setup (38 / 18 / 66), automated settlement (28 backend), and IoT v2
(43 backend / 86 IoT). Their smaller counts and historical payment units must not be
used as the current native protocol's acceptance result. Git retains those reports.

Useful unique evidence from those stages: the SQLModel seed ran twice on a fresh
database with five homes, fifteen devices and zero falsely verified wallets; an
existing-schema sentinel user survived upgrades; a disposable TLS Mosquitto test
verified scoped delivery, cross-community ACL refusal and anonymous rejection.
Simulator tests cover daily/night solar, SOC/conservation, restart determinism and
faults. Earlier physics-only timing was a microbenchmark, not a broker/database
throughput guarantee. No public meter, mutual-TLS acceptance deployment or public
network settlement is established by these checks.

Frontend route/responsive checks and the retained screenshots used local fixtures;
no formal WCAG audit or live MetaMask extension flow was run.

## Reproduce

[Getting started](getting-started.md) owns startup and finite demonstration commands.
[Development](development.md) owns test commands, fixtures and prerequisites.
Current private scenario results and encrypted wallets live under ignored
`.run/demo`; the committed evidence contains public local transaction metadata only.
Neither this documentation audit nor the prior integration published the cloud
environment.

## MQTT session recovery follow-up

After the documentation audit, publisher startup/reconnection was corrected to
wait for an acknowledged MQTT session, and the simulator overlay received a client
ID distinct from the diagnostic gateway. The IoT suite was executed: **90 passed,
85.14% coverage**. New regressions cover delayed CONNACK, failed startup cleanup,
bounded disconnected publication and preservation of the sample on reconnection.
A separate real Mosquitto stop/start probe detected disconnection, reconnected
without recreating the publisher and delivered the next acknowledged telemetry
message. Scoped Ruff, Compose configuration validation and whitespace checks passed.
This verifies local transport recovery; it does not identify the cause of a remote
user's broker disconnection or establish a new full financial scenario result.

## Named-volume persistence and isolated recovery follow-up

The earlier integration persistence probe used a host-directory bind mount. It
passed that check but did not exercise a newly created Docker named volume. A
subsequent reproduction found that `/state` was root-owned and unwritable by the
Foundry image's UID 1000. RPC health alone therefore did not establish persistence.
The one-off volume ownership initializer and state-file health condition now cover
that actual deployment boundary.

Executed for this correction:

- A fresh uninitialized named volume reproduced the unwritable state directory.
- The actual Compose initializer made a named volume writable; Anvil saved state
  periodically. After SIGKILL, genesis, deployed contract bytecode, transaction
  receipt and sender nonce were all preserved on restart.
- The complete isolated recovery command archived an existing PostgreSQL database
  and retained four original volumes. Its private dump was restored into a separate
  disposable inspection database; 33 archived users remained readable. Private
  archive/dump/settings permissions were checked.
- The replacement demo verified all five deployed contracts across another Anvil
  restart, then completed the actual MQTT/worker/native financial scenario:
  5 kWh injection, 3 kWh allocation, 0.003 ETH earned/withdrawn and 3 SUN retired.
- Three recovery safety tests passed: public configuration, public RPC endpoint,
  and an intact registry all prevent replacement before infrastructure mutation.
- Scoped Ruff, Compose validation, Markdown lint and whitespace checks passed.

This is a new local demonstration, not restoration of the old chain's contracts,
receipts or financial entitlements. No old financial rows were relabeled or imported
as new balances. No full backend/frontend suite or public network acceptance was
rerun as part of this infrastructure correction.

## Same-database recommissioning and test isolation

`make repair-demo` now supports an unused local deployment whose registry code is
missing while retaining the existing PostgreSQL database and private identities.
The integrated governed MQTT test preserves an existing address, password hash and
historical telemetry row, recreates the local contracts, verifies cursor rebinding,
then completes issuance, delivery, retirement and withdrawal. It refuses intact
registries, changed seed credentials and existing financial history. A Docker CLI
smoke test separately retained six users, five homes, password hashes and telemetry
while replacing the missing registry binding.

The backend suite passed **51 tests** and the IoT suite passed **90 tests** at
85.14% coverage. Test runners and the broker-restart case explicitly select the
`solar-prototype-tests` project: an inherited development project name can no
longer redirect their Compose operations. Development Anvil and PostgreSQL container
IDs were unchanged across the isolated full backend run. Scoped Ruff, shell syntax,
Markdown lint, local links/schema checks and whitespace validation passed.

This does not claim that a remote user's repair was already executed. The command
creates a private SQL backup before attempting changes and refuses to reuse any
recorded financial entitlement on a replacement chain.
