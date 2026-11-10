"""Pydantic schemas describing the canonical telemetry envelope.

The envelope is the wire format published to the local MQTT broker.
Any publisher must validate against it before sending, so that bad
payloads are rejected at the edge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.sensor import SensorType


class TelemetryPayload(BaseModel):
    """Common envelope around any sensor reading."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
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
        return value.astimezone(UTC)

    def to_mqtt_payload(self) -> dict[str, Any]:
        """Return a JSON-ready dict (datetime serialised as ISO-8601)."""
        payload = self.model_dump()
        payload["measured_at"] = self.measured_at.isoformat()
        payload["sensor_type"] = self.sensor_type.value
        return payload


# Backwards-compatible alias used by callers.
TelemetryEnvelope = TelemetryPayload
