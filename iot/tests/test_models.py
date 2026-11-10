"""Tests for the domain models."""

from __future__ import annotations

from decimal import Decimal

import pytest

from models.home import Home
from models.sensor import Sensor, SensorStatus, SensorType


def test_sensor_valid() -> None:
    sensor = Sensor(
        device_code="SM-Moscow-001-001",
        sensor_type=SensorType.SMART_METER,
        home_id="HOME-Moscow-001",
    )
    assert sensor.is_active
    assert sensor.status == SensorStatus.ACTIVE


def test_sensor_empty_device_code() -> None:
    with pytest.raises(ValueError, match="device_code"):
        Sensor(
            device_code="  ",
            sensor_type=SensorType.SMART_METER,
            home_id="HOME-Moscow-001",
        )


def test_sensor_mqtt_topic() -> None:
    sensor = Sensor(
        device_code="SM-Moscow-001-001",
        sensor_type=SensorType.SMART_METER,
        home_id="HOME-Moscow-001",
    )
    assert (
        sensor.get_mqtt_topic()
        == "solar/HOME-Moscow-001/SM-Moscow-001-001/telemetry"
    )


def test_home_rejects_duplicate_devices() -> None:
    sensor = Sensor(
        device_code="SM-Moscow-001-001",
        sensor_type=SensorType.SMART_METER,
        home_id="HOME-Moscow-001",
    )
    with pytest.raises(ValueError, match="Duplicate devices"):
        Home(
            home_id="HOME-Moscow-001",
            city="Moscow",
            solar_capacity_kw=Decimal("4"),
            battery_capacity_kwh=Decimal("10"),
            devices=(sensor, sensor),
        )


def test_home_get_device(sample_home: Home) -> None:
    device = sample_home.get_device("SM-TEST-001-001")
    assert device.sensor_type == SensorType.SMART_METER


def test_home_get_missing_device(sample_home: Home) -> None:
    with pytest.raises(ValueError, match="not found"):
        sample_home.get_device("NOPE")
