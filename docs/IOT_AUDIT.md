# IoT audit and verification — 10 November 2026

## Corrected defects

- Smart-meter counters were shared by all homes using a generator instance.
  Each home now owns one physical state, independent counters, battery storage and
  RNG stream; every sensor in the coordinator observes that same state.
- Grid flows were unrelated random values. Import/export now solve the complete
  generation + import + discharge = load + export + charge balance.
- Solar output occurred at night. A latitude/date/longitude solar-elevation model,
  equation-of-time correction, Colombian timezone and cloud factor now determine PV
  output. Inverter energy integrates AC output, not unrelated DC power.
- Battery SOC was a random walk independent of power. Dispatch now enforces SOC,
  efficiency and power limits, with no simultaneous charge and discharge.
- Energy accumulated on every sensor call using a configured delay. Counters now
  integrate actual elapsed simulation timestamps; first readings establish a zero
  baseline and repeated timestamps do not add energy.
- Daily inverter energy was `lifetime % 30`. Daily counters now follow local dates.
- Publisher failures were logged and discarded. QoS1/2 publication waits for broker
  acknowledgement, reports unknown outcomes, bounds the library queue and applies
  reconnect backoff. The coordinator retains the exact failed message/sequence for
  retry before generating a newer sample for that device.
- Optional atomic checkpoints retain counters, SOC, RNG state, timestamps, pending
  messages and sequences across restarts. They never contain device credentials.
- Friendly demo IDs could not identify registered UUID devices. An explicit registry
  adapter maps friendly codes to provisioned device/home UUIDs and credential env
  bindings; backend authorization remains mandatory.
- Duplicate envelopes inside one database batch attempted duplicate typed-row
  inserts. Typed rows are now inserted only once for each returned telemetry UUID.
- A cross-interval counter gap permanently blocked recovery. A new baseline now
  resumes subsequent observed deltas, without crediting the unobserved gap.
- Unrealistic cumulative jumps are rejected using elapsed time and the configurable
  MAX_METER_POWER_W (100 kW default, plus 2 Wh quantization tolerance).
- Ingestion now rejects payloads over MAX_TELEMETRY_BYTES (64 KiB default), retains
  post-commit manual acknowledgement, supports broker credentials/CA/client certs,
  and logs structured batch counts, latency and queue depth without credentials.

## Verification actually executed

- `scripts/test_iot.sh -q`: **66 passed, none skipped, 83.28% coverage** against the
  unchanged 80% gate. Tests include a full day of power conservation and SOC limits,
  optional batteries, consumer-only homes, independent counters, solar timing,
  clock restrictions, restart determinism, duplicate/fault fixtures, retry identity,
  missing acknowledgements and registry mapping.
- `scripts/test_backend.sh -q --tb=short`: **13 passed, none skipped** against real
  PostgreSQL, MQTT, Redis and Anvil. The lifecycle test now publishes every reading
  twice over MQTT, verifies unique persisted samples/intervals, rejects a forged
  topic, and completes credit issuance, trade, compensation and burn.
- Simulator Docker image built successfully with TLS verification and the managed
  CA. A container started five homes, emitted live coordinated console telemetry,
  and was stopped gracefully.
- 100 home models × 120 steps: **0.200 seconds, about 59,873 home-steps/second** on
  this host. This measures physics only, not database or broker ingestion throughput.
- Undefined-name/unused-import checks on changed IoT modules and `git diff --check`
  passed. No runtime secret files or simulator checkpoints are committed.

## Explicit boundaries

This is an approximate simulation, not calibrated metering or weather prediction.
Power is held at the current step during elapsed-time energy integration; use small
steps and aligned accounting samples. Cloud variation is seeded, not a real forecast.
Zero network losses are assumed in simulation; battery conversion losses are explicit.

The offline clock and deterministic fault transformations are test/developer APIs;
accelerated or historical clocks cannot be selected as live clocks. Normal backend
future/stale timestamp restrictions remain intact. Counter rollover without a known
hardware modulus is conservatively treated as a reset, not guessed positive energy.
Reset/gap baselines never issue energy for missing history. Full per-meter rated
power policy and persistent quality-event taxonomy remain future refinements.

The original friendly sensor codes are retained for compatibility, including legacy
MS identifiers. They are not credentials and are not automatically registered by
seed files. The legacy gRPC demo path is diagnostic; use the registered direct MQTT
path for authenticated accounting. A device registry must cover every enabled
sensor before running a provisioned multi-home simulation.

The base broker remains loopback-bound for local demonstrations. An optional
password/ACL overlay is supplied; per-device ACLs must be provisioned for real
registered identities. TLS is supported in clients but site-specific certificates
must be supplied before using an untrusted network. The disposable MQTT broker was restarted in an integration test and both publisher
and subscriber reconnected and delivered a subsequent message. Mutual-TLS
handshake scenarios were not exercised; deployment certificates remain site-specific. No claim of production broker hardening is made.


## SQLModel seed and test rewrite

The obsolete database/seeds SQL files were removed: they referenced users.id and
full_name instead of users.uid/first_name/last_name, omitted required home addresses
and MQTT client IDs, used incompatible hashes and marked placeholder wallets as
verified. src.seed now constructs canonical SQLModel entities in one transaction.
It seeds five users, five homes, memberships/nodes, fifteen devices, and unverified
wallets. Optional explicit device authorization derives per-device credentials
from a runtime key and exports the complete simulator UUID registry privately.
It does not fabricate measurements, mintable credits or financial records.

The seed CLI was run twice against a fresh migrated PostgreSQL database: the final
counts were 5 homes, 15 devices and 0 verified wallets, with private credential-file
permissions verified. A fresh-process mapper test catches missing model imports
that would be hidden by a full suite's imports. Seed tests preserve existing
passwords and revoked authorizations, while a seeded physics-to-ingestion test
checks observed export eligibility and persistent duplicate prevention.

IoT generator tests were rewritten: identical repeated timestamps no longer serve
as evidence of integration, and inverter assertions use AC output over actual
elapsed time. The backend test runner creates and drops only its own newly named
disposable database, so previously persisted intervals cannot satisfy a broken test.
See database/seeds/README.md for explicit seed configuration and security defaults.
