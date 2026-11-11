# IoT metering, simulation and verification

The current path is simulation/physical device → authenticated MQTT → versioned
schema → persisted evidence → counter processing → interval verification → governed
settlement batch → authorized SUN issuance. MQTT callbacks never mint, submit a
batch or spend ETH. A PENDING SQL energy credit is eligibility evidence, not a token.

## Shared physical simulation

`iot/simulator/physics.py` supplies every sensor in a home from the same physical
state. Homes have independent deterministic RNGs and stable sensor associations.
The configurable profiles are consumer, solar producer, prosumer, battery prosumer
and small commercial installation. The example catalogue uses the existing demo
registry identities and capacities; adding a home does not require a new class.

| Capability | Existing channel |
| --- | --- |
| PV power, cumulative generation, inverter/temperature | solar_inverter |
| Household load (consumption_power_w) and cumulative consumption | smart_meter |
| Grid import/export power and cumulative counters | smart_meter |
| SOC, capacity, charge/discharge power, efficiency and cumulative counters | battery_monitor |
| Irradiance, weather and panel temperature | weather_sensor |

active_power_w remains signed net grid power; it is distinct from household load.
Only installed capabilities are emitted. A consumer needs no inverter or battery.
Cali solar elevation uses date/location and local solar time; clouds vary gradually,
loads have morning/evening or business-hour peaks and appliance variability. The
AC bus obeys generation + discharge + import = load + charge + export. PV conversion
and battery storage efficiencies are modeled separately; storage cannot exceed its
SOC bounds. Counter integration uses elapsed UTC time and at most 60-second physical
substeps, including long accelerated samples. These are reproducible synthetic
profiles, not forecasts or calibrated physical measurements.

### Modes and faults

Normal mode is REALTIME, speed 1, faults disabled. Accelerated or deterministic mode
requires an explicit timezone-aware start and v2 metadata. Deterministic mode advances
without wall-clock dependence. All simulator output says source=SIMULATED; its mode
is carried on the wire and into evidence. Offline modes can be audited but never
supply settlement input. The old protobuf/gRPC path remains a v1 diagnostic path;
registered or offline simulation uses direct v2 MQTT so provenance is not lost.

From `iot/`, a bounded offline smoke run needs no broker or credentials:

```sh
USE_GRPC=false PUBLISHER=console \
HOME_CATALOGUE_FILE=examples/community-profiles.json \
SIMULATION_MODE=DETERMINISTIC SIMULATION_SPEED=60 \
SIMULATION_START=2026-11-10T17:00:00Z RANDOM_SEED=42 \
SEQUENCE_OFFSET=0 MAX_CYCLES=2 python -m simulator.main
```

`FAULT_SCENARIO` supports device_outage, mqtt_disconnection, duplicate, packet_loss,
invalid_payload, counter_reset, clock_drift, export_spike, unauthorized_device,
missing_interval and out_of_order (legacy aliases remain supported). `FAULT_DEVICE`
optionally selects one sensor code; other homes/devices continue normally. Faults
require offline mode and are rejected in normal operation. `PUBLISHER=console`
keeps experiments off a live broker. The validated publisher may reject malformed
fault fixtures at the edge; backend rejection tests also exercise raw MQTT/envelopes.

Set `CHECKPOINT_PATH` to preserve physical counters, battery state, RNG, per-device
sequences and pending deliveries. Docker mounts persistent simulation state. A
failed publish retries the original message/sequence before generating a replacement.
Without a checkpoint, the normal CLI uses an epoch sequence offset; a replaced meter
requires a new commissioned identity and establishes a new counter baseline.

## Commissioning and versioned wire format

Every operational meter must have an active database device, registered node,
community authorization, current on-chain member/meter authorization where governed,
and a matching scoped device credential. Connecting to MQTT or copying a device ID
does not establish any of these permissions. Owners can create pending devices and
disable them; they cannot activate themselves. Weather registration now uses the
existing WEATHER_SENSOR alias and canonical weather_sensor channel.

A device has a commissioned PHYSICAL or SIMULATED source. Fresh SQLModel demo seed
devices are SIMULATED, and their inactive draft community explicitly allows local
simulation. Existing records and revoked credentials are not silently reclassified
or reactivated. Existing v1 commissioned devices keep compatibility; review the
source of older demo records before using v2. Use a new seed output directory if
upgrading an older registry file: existing private output files are preserved.

For a new simulated community, create it with allow_simulated_telemetry=true before
submitting its governance proposal. The consent enters the proposal policy hash and
immutable settlement policy snapshot. It does not activate the community. Simulated
settlement evidence is accepted only for an opted-in local Anvil community. Sepolia
rejects simulated sources even if this flag is set. The server's commissioned source
wins over a publisher's claim; changing a JSON source tag cannot turn a virtual meter
into a physical one.

v2 adds to the v1 device/home/type/sequence/time/data fields:

- schema_version="2.0" and UUID message_id.
- Registered community_id and node_id.
- source, simulation_mode and optional quality indicators.
- Exact units for every measurement key: kWh, W, V, A, Hz, %, degC, W/m2, etc.

The canonical topic is `solar/{community_uuid}/{node_uuid}/{public_device_uuid}/telemetry`.
RegisteredPublisher translates friendly catalogue codes using the provisioned public
registry; credentials are read from environment bindings, never stored in the registry
or checkpoints. Both topic and envelope must match the registered physical association.
Database device IDs used in authenticated APIs differ from public wire device UUIDs.

v1 `solar/{home_uuid}/{device_uuid}/telemetry` remains supported for existing devices.
Unknown measurement fields, nonfinite values, wrong units, malformed timestamps,
unreasonable ranges and database-overflow-sized counters are rejected. Authenticated
invalid measurements retain a safe audit record; credentials are never included.

## Counter processing and quality

The current verification calculation version is v3-validated-grid-counters. Older
completed interval versions remain unchanged. Counter snapshots and interval increments commit together. The first reading is a
baseline. Duplicate sequences or message IDs cannot add a delta. Out-of-order data
is rejected. Missing interval coverage and counter resets establish a new baseline
without adding energy. A rollover is accepted only with a commissioned positive
counter_modulus_wh, values near its boundaries, and a plausible power-bound delta.
Leave the modulus unset when the physical meter specification is not known; a fall
in a counter is then a reset, never invented export. The commissioning authority
controls this hardware metadata, not telemetry payloads.

Battery v2 cumulative charge/discharge counters are persisted and differenced. Older
power-only samples retain bounded trapezoidal integration. PV generation alone is
never eligible export. Interval eligibility uses the authoritative grid meter and
requires processed samples at both exact interval boundaries after the grace period.
Pending samples delay finalization; invalid/reset/gap samples reject the interval;
missing boundaries produce INCOMPLETE rather than mintable evidence.

TelemetryAssessment retains hashed evidence and counted occurrences with VALID,
INVALID, DUPLICATE, UNAUTHORIZED, STALE, SUSPECT, OUT_OF_ORDER, COUNTER_RESET,
COUNTER_GAP and configured COUNTER_ROLLOVER states. Malformed MQTT bytes are hashed
and audited before acknowledgement. Repeated assessments increment counts rather
than creating unbounded identical rows. Schema-valid measurements remain in the
existing telemetry/typed sensor tables; no second mapping is introduced.

Authenticated contradictory smart-meter evidence quarantines overlapping intervals
as DISPUTED and rejects still-unissued eligibility. New native service operations
are withheld, including an already-journalled signature checked before broadcast.
Already mined token transfers/payments remain actual chain history; correction
requires explicit review and governance safeguards, not silent reversal. A held
service nonce may require operator intervention before later queued service work
can proceed. Reserve cancellation and community suspension remain explicit actions.

## Transport and observability

Publishers use QoS 1/2, bounded outgoing queues, bounded acknowledgement waits and
reconnection backoff. Initial connection retries are bounded at the publisher and
stop-aware at the subscriber. Keepalive and retained online/last-will gateway status
use `solar/status/{client_id}`; these are liveness signals, never energy evidence.
Device health derives from authenticated fresh telemetry. Duplicate/rejected bodies
cannot refresh last-authenticated telemetry. The subscriber acknowledges data only
after its database transaction; queue pressure leaves data unacknowledged and
reconnects the persistent session for redelivery after draining.

Authenticated reads (own device only):

- `GET /api/v1/iot/devices/{database_device_id}/health`: source, online/last telemetry,
  quality counts, latency, interval quality and settlement-input readiness.
- `GET /api/v1/iot/devices/{database_device_id}/quality?limit=50&offset=0`: bounded
  credential-free audit evidence, reasons, hashes and occurrence counts.

Settlement batches retain source/schema/mode references as well as interval, node,
meter, telemetry IDs and hashes. Finalized governance and financial conditions are
still required after an interval becomes ready; see [community settlement](community-settlement.md).

## Broker ACLs and TLS

The default broker is a loopback development fixture. For authenticated device use,
render exact grants from the public registry:

```sh
python scripts/provision_mqtt_acl.py /path/to/registry.json \
  --output /path/to/new-acl --gateway-user solar-gateway
```

Each meter principal can write only its exact community/node/device topic. A named
multi-device gateway gets only the registry cohort's exact topics. The subscriber
has read permissions. Generate a Mosquitto password file with the standard interactive
mosquitto_passwd utility for the corresponding principals; the script handles no
passwords. Set MQTT_USERNAME and MQTT_CLIENT_ID consistently so the principal's
last-will topic is also permitted.

`compose.mqtt-secure.yml` overlays the prototype with an authenticated TLS listener.
Provide MQTT_PASSWORD_FILE, MQTT_ACL_FILE, MQTT_TLS_DIRECTORY (ca.crt/server.crt/
server.key), and MQTT_SUBSCRIBER_PASSWORD through the operator's private environment.
Mounted files must be readable by the broker's UID; do not put keys or passwords in
Git. Client TLS verifies the CA and hostname. For the simulator overlay, set
SIMULATOR_MQTT_PORT=8883, SIMULATOR_MQTT_TLS=true and SIMULATOR_CA_FILE to the public CA,
plus scoped MQTT credentials in the private simulator environment file. TLS is not
silently disabled to make a connection succeed.

The automated security test starts a disposable real TLS Mosquitto broker, verifies
accepted scoped delivery, rejects a cross-community MQTT v5 publish and rejects
anonymous access. No public broker, production identity or external device is used.

## Provisioning sequence and payload example

1. Create an owned home and pending device through the authenticated API.
2. Propose the community with its physical boundary and source policy; governance
   reviews, approves, configures its price and activates an appointed operator.
3. Verify the owner's wallet and synchronize approved registry membership.
4. Register the physical node, authorize its public meter UUID through governance,
   and synchronize the node owner.
5. An operator binds the internal device UUID to that node with a fresh 32+ character
   credential through `POST /api/v1/communities/nodes/{node_id}/meters`.
6. Configure the device's exact topic, credential and independent broker ACL.

This illustrative v2 body follows the
[backend validator](../apps/backend/src/iot/telemetry_validator.py). UUIDs must be
replaced with commissioned identities; the timestamp must be current and aware.
The credential below is a placeholder, not a working authentication value.

```json
{
  "schema_version": "2.0",
  "message_id": "11111111-1111-4111-8111-111111111111",
  "community_id": "22222222-2222-4222-8222-222222222222",
  "node_id": "33333333-3333-4333-8333-333333333333",
  "home_id": "44444444-4444-4444-8444-444444444444",
  "device_id": "55555555-5555-4555-8555-555555555555",
  "sensor_type": "smart_meter",
  "source": "SIMULATED",
  "simulation_mode": "REALTIME",
  "sequence_number": 1,
  "measured_at": "2026-11-11T17:00:00Z",
  "credential": "REPLACE_WITH_A_PRIVATE_COMMISSIONED_CREDENTIAL",
  "units": {
    "grid_export_energy_kwh": "kWh",
    "grid_import_energy_kwh": "kWh",
    "consumption_energy_kwh": "kWh"
  },
  "data": {
    "grid_export_energy_kwh": 5,
    "grid_import_energy_kwh": 0,
    "consumption_energy_kwh": 1
  }
}
```

Publish on the topic containing that community/node/public-device tuple. A single
cumulative reading establishes a baseline; the example alone cannot create 5 kWh
of eligible injection. Matching processed boundary readings are required.

The default simulator cycle is 15 seconds; this is separate from the default
900-second accounting interval. Configuration, complete simulator controls and
transport security settings are defined in [configuration](configuration.md).
Use `make simulate` after `make demo` for the registered continuous fixture; see
[getting started](getting-started.md#start-continuous-simulation).
