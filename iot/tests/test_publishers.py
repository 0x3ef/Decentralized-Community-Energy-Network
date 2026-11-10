"""Tests for publishers (no network)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from models.sensor import SensorType
from publishers.console_publisher import ConsolePublisher


def test_console_publisher_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = ConsolePublisher()
    with caplog.at_level(logging.INFO):
        publisher.publish(
            "solar/HOME-1/SM-1/telemetry",
            {
                "device_id": "SM-1",
                "home_id": "HOME-1",
                "sensor_type": SensorType.SMART_METER.value,
                "sequence_number": 1,
                "measured_at": datetime.now(UTC).isoformat(),
                "schema_version": "1.0",
                "data": {"voltage_v": 120.0},
            },
        )
    assert any("solar/HOME-1/SM-1/telemetry" in r.message for r in caplog.records)
