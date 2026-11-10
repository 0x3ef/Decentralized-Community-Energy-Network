"""Tests for the telemetry schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from models.sensor import SensorType
from schemas.telemetry import TelemetryPayload


def test_valid_payload() -> None:
    payload = TelemetryPayload(
        device_id="SM-1",
        home_id="HOME-1",
        sensor_type=SensorType.SMART_METER,
        sequence_number=1,
        measured_at=datetime.now(UTC),
        data={"voltage_v": 120.0},
    )
    assert payload.schema_version == "1.0"
    assert payload.to_mqtt_payload()["sensor_type"] == "smart_meter"


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        TelemetryPayload(
            device_id="SM-1",
            home_id="HOME-1",
            sensor_type=SensorType.SMART_METER,
            sequence_number=1,
            measured_at=datetime.now(),
            data={},
        )


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        TelemetryPayload(
            device_id="SM-1",
            home_id="HOME-1",
            sensor_type=SensorType.SMART_METER,
            sequence_number=1,
            measured_at=datetime.now(UTC),
            data={},
            unknown="boom",
        )
