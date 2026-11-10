"""Pydantic schemas describing the canonical telemetry envelope.

The envelope is the wire format published to the local MQTT broker.
Any publisher must validate against it before sending, so that bad
payloads are rejected at the edge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.sensor import SensorType


class TelemetryPayload(BaseModel):
    """Common envelope around any sensor reading."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0", "2.0"] = "1.0"
    message_id: str | None = None
    community_id: str | None = None
    node_id: str | None = None
    source: Literal["PHYSICAL", "SIMULATED"] | None = None
    simulation_mode: Literal["REALTIME", "ACCELERATED", "DETERMINISTIC"] = "REALTIME"
    units: dict[str, str] | None = None
    quality: list[str] = Field(default_factory=list)
    device_id: str = Field(min_length=1)
    home_id: str = Field(min_length=1)
    sensor_type: SensorType
    sequence_number: int = Field(ge=0)
    measured_at: datetime
    data: dict[str, Any]

    @field_validator("measured_at")
    @classmethod
    def _ensure_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware")
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError) as exc:
            raise ValueError("Timestamp is outside the supported UTC range") from exc

    @model_validator(mode="after")
    def versioned(self):
        if self.schema_version == "2.0" and (
            not all((self.message_id, self.community_id, self.node_id, self.source))
            or self.units != {k: measurement_unit(k) for k in self.data}
        ):
            raise ValueError(
                "v2 requires complete identities, provenance and exact measurement units"
            )
        return self

    def to_mqtt_payload(self) -> dict[str, Any]:
        """Return a JSON-ready dict (datetime serialised as ISO-8601)."""
        payload = self.model_dump()
        payload["measured_at"] = self.measured_at.isoformat()
        payload["sensor_type"] = self.sensor_type.value
        return payload


# Backwards-compatible alias used by callers.
TelemetryEnvelope = TelemetryPayload


def measurement_unit(field: str) -> str:
    for suffix, unit in (
        ("_kwh", "kWh"),
        ("_w_m2", "W/m2"),
        ("_power_w", "W"),
        ("_voltage_v", "V"),
        ("_current_a", "A"),
        ("_v", "V"),
        ("_a", "A"),
        ("_hz", "Hz"),
        ("_pct", "%"),
        ("_c", "degC"),
        ("_m_s", "m/s"),
    ):
        if field.endswith(suffix):
            return unit
    return {
        "power_factor": "1",
        "operating_state": "bool",
        "alarm_code": "text",
        "status": "text",
    }.get(field, "unknown")
