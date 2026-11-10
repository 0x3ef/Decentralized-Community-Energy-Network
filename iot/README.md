# Coordinated IoT simulation

Current implementation and evidence: [IoT audit](../docs/IOT_AUDIT.md).
All sensors in a home observe one model. Default location is Cali, Colombia;
legacy MS sensor identifiers are preserved as stable labels, not authorization.

## Run locally

```bash
source .venv/bin/activate
cd iot
USE_GRPC=false PUBLISHER=console RANDOM_SEED=42 python -m simulator.main
```

For authenticated accounting, register homes/devices and authorize meters through
community APIs first. Copy `examples/registry.example.json` outside the checkout,
replace the example UUIDs with actual provisioned identities, and add an entry for
**each enabled sensor**. Entries reference credential environment names, not values.
Supply those values securely in the runtime environment, then run:

```bash
USE_GRPC=false MQTT_HOST=127.0.0.1 DEVICE_REGISTRY=/private/registry.json \
  CHECKPOINT_PATH=/private/state/simulator.json python -m simulator.main
```

`HOME_PROFILES_JSON` maps friendly home IDs to HomeProfile overrides, such as
`{"HOME-MS-003":{"baseline_w":1200,"peak_w":3000,"occupancy":2}}`.
Profiles accept latitude, longitude, IANA timezone, demand, SOC, efficiencies and
battery power limits. `RANDOM_SEED` controls independent per-home RNG streams.
Use `Simulator.simulate_cycle(aware_datetime)` for deterministic offline steps;
`SimulationClock(start, speed, offline=True)` supports accelerated test clocks.
Do not publish accelerated future data to normal ingestion.

`simulator.faults.inject` provides optional duplicate, outage, packet-loss,
out-of-order, reset, drift, delay, invalid-schema and spike transformations.
It never activates automatically. Checkpoints preserve original unsent messages;
after an unknown acknowledgement, retrying can redeliver the same sequence and
backend persistent deduplication prevents duplicate accounting.

## Docker

Use the root `compose.prototype.yml` together with `compose.iot.yml`, configure
SIMULATOR_REGISTRY_FILE and a private SIMULATOR_ENV_FILE, and enable the simulation
profile. The simulator runs all configured homes in one scheduler and stores state
in a dedicated volume. The optional `compose.mqtt-auth.yml` mounts provisioned
Mosquitto password and ACL files; `secure/acl.example` demonstrates exact-device
write permissions and subscriber read permissions. Adapt it to the registry.

MQTT_USERNAME/MQTT_PASSWORD configure broker login. IoT MQTT_TLS, MQTT_CA_CERT,
MQTT_CLIENT_CERT and MQTT_CLIENT_KEY enable verified mutual TLS. The backend uses
MQTT_TLS_CA, MQTT_TLS_CERT and MQTT_TLS_KEY for equivalent subscriber configuration.
Never disable certificate verification or place credentials in checked-in JSON.

## Tests

From the repository root, activate the venv and run `./scripts/test_iot.sh -q` and
`./scripts/test_backend.sh -q`. The former starts its own gateway against the local
broker; the latter uses isolated PostgreSQL/MQTT/Redis/Anvil containers.

---

The following original module reference is retained for context; legacy gRPC demo
instructions do not provision authorized UUID identities or credentials.

# IoT Simulation and Telemetry Gateway

The `iot/` package provides a deterministic, local-first telemetry
environment for the Solar Energy Market. It models residential sensors,
transports their readings over gRPC, validates them at the gateway, and
publishes one canonical JSON envelope to the local Mosquitto broker.

## Runtime flow

```text
Simulator -> gRPC gateway -> Mosquitto -> backend MQTT subscriber -> PostgreSQL
```

The simulator does not publish directly to MQTT when `USE_GRPC=true`.
Each sensor generator creates one reading per cycle and sends it to the
matching gRPC service. The gateway is the single edge where protobuf
requests become validated MQTT envelopes. This keeps direct simulation
and real device traffic on the same backend ingestion path.

## Simulated devices

`config/homes.py` is the authoritative demo catalogue. Device identifiers
match the database seed convention:

```text
<sensor-prefix>-<city-code>-<home-suffix>-<index>
```

The generators model:

- **Smart meters:** voltage, frequency, power factor, signed net power,
  import/export power, and monotonic cumulative energy counters.
- **Solar inverters:** DC/AC power, efficiency, temperature, operating
  state, and lifetime energy accumulated using the configured interval.
- **Weather stations:** daylight irradiance, ambient/panel temperature,
  humidity, and wind.
- **Battery monitors:** state of charge, voltage, charge/discharge power,
  temperature, and available energy.

Values use bounded random walks where continuity matters. A random seed
can be supplied for repeatable test runs.

## Configuration

Copy `.env.example` to `.env` when running the package outside Compose.
Important settings are:

| Variable | Default | Description |
|---|---:|---|
| `INTERVAL_SECONDS` | `15` | Delay between simulation cycles |
| `RANDOM_SEED` | empty | Optional seed for reproducible readings |
| `SEQUENCE_OFFSET` | current epoch | Starting sequence offset; set it explicitly for replay tests |
| `USE_GRPC` | `true` | Send readings through the gateway |
| `GATEWAY_ADDRESS` | `gateway:50051` | gRPC gateway address |
| `PUBLISHER` | `mqtt` | Gateway output: `mqtt` or `console` |
| `MQTT_HOST` | `mosquitto` | Local broker hostname |
| `MQTT_PORT` | `1883` | Local broker port |
| `MQTT_QOS` | `1` | MQTT delivery QoS |

For Docker Compose, `GATEWAY_ADDRESS=gateway:50051` and
`MQTT_HOST=mosquitto` are supplied by the service environment.

## Commands

```bash
make protos       # regenerate Python gRPC stubs
make test         # unit tests
make test-all     # unit and integration tests in Compose
make lint         # Ruff checks
make typecheck    # mypy
make up           # start the complete local stack
make logs         # follow service logs
```

Generated files under `grpc_client/` must be regenerated after editing
`protos/sensor.proto`. The checked-in stubs are also generated during the
IoT Docker build, so a clean checkout remains buildable.

## Telemetry envelope

The gateway publishes to:

```text
solar/<home_id>/<device_id>/telemetry
```

Every message has `schema_version`, `home_id`, `device_id`,
`sensor_type`, a monotonic per-device `sequence_number`, a timezone-aware
`measured_at`, and sensor-specific `data`. See
`docs/iot/topics.md` for the complete schema and topic contract.

## Troubleshooting

- If the simulator logs gRPC connection errors, check
  `docker compose ps gateway` and verify `GATEWAY_ADDRESS`.
- If messages are generated but not persisted, inspect both the gateway
  and subscriber logs; the subscriber must be connected to `solar/#`.
- Use `RANDOM_SEED=42` to reproduce a failing simulation sequence.
- Use `USE_GRPC=false` only for generator-level development; it bypasses
  the gateway and does not exercise the production ingestion path.
