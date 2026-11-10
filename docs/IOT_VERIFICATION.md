# IoT verification — 2026-11-10

Executed locally against the installed Python environment, PostgreSQL, Redis,
Mosquitto and Anvil:

| Check | Result |
| --- | --- |
| Backend and integrated IoT/native settlement | 43 passed |
| IoT simulator, schemas and transport suite | 86 passed; 84.59% coverage |
| Existing smart contract suite | 38 passed |
| Simulator container build/run | Passed; 30 v2 offline messages |
| Development schema/API | Migrated through 20261110_load_power |
| Deterministic CLI smoke | 5 homes, 30 v2 messages, explicit offline provenance |
| Targeted Ruff and Python compilation | Passed |

The backend suite covers v2 bindings/units, duplicated sequence/message IDs, rejected
credentials, cross-community mismatch, source mismatch, offline provenance, simulated
Sepolia rejection, unknown fields, negative and oversized counters, stale/out-of-order
samples, missing intervals, resets and configured rollover. Invalid evidence cannot
produce pending energy credits. Authenticated contradictory evidence quarantines a
closed interval and prevents further native worker operations. Audit reads omit
credentials and rejected attempts do not refresh device health.

The legacy accounting test now separates late contradictory evidence from the valid
mint/payment scenario: that incident is quarantined and cannot justify approval.

The existing complete native settlement scenario now uses explicitly commissioned
SIMULATED v2 meters in an opted-in Anvil community: 5 kWh injection, 3 kWh consumption,
5 SUN issuance after governance finalization, 3 SUN funded delivery for 0.003 test ETH,
retirement without another payment, replay/crash recovery and reorganization handling.

The new real broker test creates disposable TLS credentials and a private test broker.
It proves scoped authenticated delivery, cross-community ACL refusal and anonymous
connection refusal with normal certificate validation. The existing restart test
still exercises subscriber/publisher recovery against the disposable MQTT broker.

Simulator tests exercise all five catalogue profiles, independent reproducible home
states, daily/night solar behavior, long elapsed-time integration, battery SOC and
energy conservation, stable device associations, exact UTC clocks, v2 registry/topic
binding and the deterministic fault matrix. The CLI was run with PUBLISHER=console;
its offline data was not sent to a live device deployment.

The schema migration adds source/consent metadata, message-ID uniqueness, battery
counters and retained telemetry assessments without deleting historical data. Older
source metadata and seed registry outputs are intentionally not silently rewritten.

Local tests do not establish the truth or calibration of physical measurements.
Commissioning, evidence review and authorized governance remain required. No public
Sepolia deployment or independent security audit was performed. The TLS deployment
overlay requires operator-provided certificates and private broker credentials.
