Current v2 protocol and operating instructions: [DEPIN_IOT.md](DEPIN_IOT.md).
The following describes legacy v1 compatibility.

# IoT telemetry

Telemetry envelopes contain `schema_version`, `device_id`, `home_id`, `sensor_type`, `sequence_number`, `measured_at`, and typed `data`. Supported sensors are smart meters, solar inverters, weather sensors, and battery monitors.

The validator rejects unknown schema versions, malformed timestamps, invalid ranges, and unknown sensor types. The subscriber persists invalid envelopes for audit when the envelope identity is usable, skips unknown devices, and ignores duplicate sequence numbers. Device time is retained separately from `received_at` so delayed and out-of-order messages remain observable.

Homes without batteries are valid; battery readings are optional and never required for aggregation.
