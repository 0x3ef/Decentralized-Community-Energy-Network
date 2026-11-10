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
