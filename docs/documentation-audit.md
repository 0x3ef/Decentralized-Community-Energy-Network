# Documentation audit

## Result

The audit replaces 33 tracked Markdown files with 14 English Markdown files: the
root README, root security guide and twelve focused documents. Canonical topic
ownership is indexed in the [README](../README.md#documentation). No application
behavior, contract, migration, legal notice or Git history is deleted.

Existing non-Markdown screenshots, public transaction evidence, SQL/OpenAPI
snapshots and the old `.mmd` diagram remain. Their historical status is explicit;
current schema/API references do not depend on them. The Alembic extensionless
README is retained as a package-local note. No package manifest or automated tool
requires the removed module READMEs.

## Original-file disposition

Each original Markdown file was read before deletion. MERGE means its useful
content moved to the destination and its old path was removed. Earlier test
counts are preserved as scoped history instead of parallel current status pages.

| Original path | Action | Destination and reason |
| --- | --- | --- |
| `README.md` | REWRITE | Concise entry point, current native workflow and canonical index |
| `docs/README.md` | MERGE | Root README; duplicate project/setup guide with superseded stack claims |
| `docs/ARCHITECTURE.md` | MERGE | `architecture.md`; partial architecture and mandatory-gRPC assumption |
| `docs/PROTOTYPE_ARCHITECTURE.md` | MERGE | `architecture.md`; retain process/outbox rationale, replace old USDx flow |
| `docs/architecture_decisions.md` | MERGE | `architecture.md`; preserve useful decisions and explain superseded recommendations |
| `docs/DEVELOPMENT.md` | MERGE | `development.md`; correct host integration-test workflow and missing test filenames |
| `docs/DEPLOYMENT.md` | MERGE | `deployment.md`; correct setup/deployment separation |
| `docs/SEPOLIA_DEPLOYMENT.md` | MERGE | `deployment.md`; retain public preflight/commissioning runbook and mark unexecuted public steps |
| `docs/API.md` | MERGE | `api.md`; replace invented plural routes and wrong documentation URLs |
| `docs/AUTHENTICATION.md` | MERGE | `api.md`, root security guide; correct bcrypt/JWT behavior |
| `docs/database_api_mapping.md` | MERGE | `database.md`, `api.md`; remove nonexistent package paths/tables/endpoints |
| `docs/DATABASE.md` | MERGE | `database.md`; current SQLModel keys, migrations, types and ER overview |
| `docs/COMMUNITY_ACCOUNTING.md` | MERGE | `community-settlement.md`, `blockchain.md`; separate historical dual-token policy from native accounting |
| `docs/ENERGY_PROCESSING.md` | MERGE | `iot.md`, `community-settlement.md`; integrate counter rules and exact allocation |
| `docs/AUTOMATED_SETTLEMENT.md` | MERGE | `community-settlement.md`, `api.md`, `configuration.md`; one owner per policy/routes/settings subject |
| `docs/NATIVE_ETH_PROTOCOL.md` | MERGE | `blockchain.md`; retain native invariants, correct explicit governance authorities |
| `docs/BLOCKCHAIN_INTEGRATION.md` | MERGE | `blockchain.md`; remove obsolete owner-mint/native-marketplace deployment claims |
| `docs/MARKETPLACE.md` | MERGE | `blockchain.md`, `database.md`; historical mechanism is not the active protocol |
| `docs/REDEMPTIONS.md` | MERGE | `blockchain.md`, `database.md`; distinguish old redemption from consumption retirement |
| `docs/IOT_TELEMETRY.md` | MERGE | `iot.md`; fold v1 compatibility into the versioned wire reference |
| `docs/DEPIN_IOT.md` | MERGE | `iot.md`; preserve commissioning, quality, TLS/ACL and physical simulation detail |
| `docs/IOT_AUDIT.md` | MERGE | `iot.md`, `verification.md`; preserve physics/recovery/seed evidence, remove obsolete current limitations |
| `docs/IOT_VERIFICATION.md` | MERGE | `verification.md`; retain v2/TLS evidence with its historical scope |
| `docs/SETTLEMENT_VERIFICATION.md` | MERGE | `verification.md`; retain crash/reorg/funding evidence without stale suite totals |
| `docs/VERIFICATION.md` | MERGE | `verification.md`; identify USDx-era execution as historical |
| `docs/INTEGRATION_REPORT.md` | MERGE | `verification.md`; retain latest actual native execution and public-deployment blocker |
| `docs/SECURITY.md` | MERGE | Root `SECURITY.md`; consolidate short general guidance |
| `docs/SECURITY_AND_TRUST.md` | MOVE/REWRITE | Root `SECURITY.md`; retain trust/recovery assumptions and add actual auth gaps |
| `apps/frontend/README.md` | MERGE | `development.md`, `configuration.md`, `blockchain.md`; retain UI architecture, signing and bounded views |
| `apps/frontend/VERIFICATION.md` | MERGE | `verification.md`, `development.md`; preserve visual evidence links and extension/WCAG limits |
| `contracts/README.md` | MERGE | `blockchain.md`, `development.md`; replace incorrect three-contract/backend-mint overview |
| `database/seeds/README.md` | MERGE | `getting-started.md`, `configuration.md`; preserve plain-seed safety and distinction from governed bootstrap |
| `iot/README.md` | MERGE | `iot.md`, `configuration.md`, `development.md`; remove duplicate setup, broken topic link and legacy default-gRPC instructions |

The only non-Markdown maintenance changes are matching environment **examples** and
the setup script's printed documentation path. Private runtime files are untouched.
The IoT example now matches the implemented direct-MQTT default instead of selecting
the historical gRPC path implicitly.

## Important factual corrections

- Current backend code is `apps/backend/src`, not `apps/backend/app/db/models`.
  The schema begins at revision `6da8fac7d51a` and currently ends at
  `20261111_chain_identity`; no current `0001_backend_baseline` exists.
- User keys are `users.uid`; typed sensor tables are `smart_meter`, `inverter`,
  `battery`, `weather`. Earlier `home_members`, refresh-token and issuance tables
  are not current SQLModel tables.
- Native monetary quantities use integer wei / SQL NUMERIC(78,0), not a universal
  NUMERIC(38,18) monetary column. SUN remains 18-decimal credit accounting.
- Authentication is bcrypt plus signed access/refresh JWTs and Redis JTI revocation,
  not Argon2 or opaque rotating refresh tokens.
- API paths use `/auth/signup`, `/home/`, `/device/device` and `/api/v1/docs`.
  There is no active redemption router or public global community directory.
- `make setup` starts/migrates services; `make demo` deploys/commissions separately.
  Backend integration tests execute in the host virtual environment against Docker
  test services. Database/Redis ports are not published by the canonical dev stack.
- SUN/native ETH settlement is active; historical USDx/COPx and payout artifacts are
  not described as native money or new native-marketplace functionality.
- Governance proposer/executor addresses are explicit. Local zero-delay governance
  differs from public minimum delays. A community operator is not a registrar.
- Direct registered v2 MQTT is the canonical simulator path. Simulated evidence is
  local-only; Sepolia requires physical sources even with simulation consent.
- TimescaleDB is an image capability; current migrations create no hypertables or
  retention policy. Historical SQL, YAML and ER artifacts are explicitly noncanonical.
- Vite configuration is public and baked at build time. Compose interpolation and
  backend service `env_file` precedence are separate configuration surfaces.

## Validation in this documentation change

Executed during this audit:

| Check | Actual result |
| --- | --- |
| Markdownlint CLI2 0.22.0 / markdownlint 0.40.0 | All 14 files passed; line-length and table-alignment style rules disabled |
| Custom relative-link/heading check | 99 local links and anchors resolved |
| FastAPI route comparison | 47 documented method/path pairs matched the imported current application |
| OpenAPI snapshot comparison | Frontend snapshot exactly matched `app.openapi()` |
| Pydantic example validation | Both API JSON examples and the typed v2 MQTT packet passed; credential removed before sanitized-schema validation |
| SQLModel metadata comparison | Documented table names and ER foreign-key directions matched the 43 registered tables |
| Settings/template checks | All backend/IoT Settings names covered; backend templates match; all template keys recognized |
| Template-generation fixture | Two runs preserved generated values and mode 0600; backend and IoT Settings validated |
| Shell/Make inspection | 18 shell fences passed `bash -n`; all 15 documented Make goals resolved in dry run; setup script syntax passed |
| Mermaid 11.15.0 parser | All four diagrams parsed successfully |
| Staged secret scan and whitespace check | Known private runtime values/access tokens absent; no private-key blocks; `git diff --cached --check` passed |

The schema and route checks imported application code without accessing a live
database. The MQTT schema check does not establish credential authorization or
current timestamp freshness. The local HTTP service was unavailable during this
audit, so no new live health/startup or full application suite success is claimed.
Previously executed full-stack results remain scoped to [verification](verification.md).
Deployment/broadcast examples were source-checked, not executed.

Markdown tools were installed in a temporary audit directory; no documentation
website, runtime dependency or package lockfile was introduced.

## Remaining gaps

No configured/funded Sepolia deployment, public explorer verification, installed
MetaMask-extension acceptance, calibrated physical metering, independent security
audit, production infrastructure acceptance or formal WCAG audit is evidenced.
Public deployment commands are checked against code/configuration, not executed
against a public network. External faucets and mail delivery are not assumed.

No repository-wide license or official private disclosure contact exists in the
tracked tree. This audit invents neither. Historical non-Markdown artifacts remain
in place as requested; regenerating or removing them needs separate implementation
scope. Future maintenance follows [development](development.md#documentation-maintenance).
