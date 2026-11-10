"""Tests for sensor generators."""

from __future__ import annotations

from datetime import datetime

import pytest

from generators import (
    BatteryGenerator,
    SmartMeterGenerator,
    SolarInverterGenerator,
    WeatherGenerator,
)
from models.home import Home
from models.sensor import SensorType


@pytest.fixture()
def home() -> Home:
    from config.homes import build_home

    return build_home("HOME-T-001", "Test", solar_kw=5.0, battery_kwh=10.0)


@pytest.mark.parametrize(
    ("cls", "sensor_type"),
    [
        (SmartMeterGenerator, SensorType.SMART_METER),
        (SolarInverterGenerator, SensorType.SOLAR_INVERTER),
        (WeatherGenerator, SensorType.WEATHER_SENSOR),
        (BatteryGenerator, SensorType.BATTERY_MONITOR),
    ],
)
def test_generator_returns_dict(
    cls, sensor_type: SensorType, home: Home, fixed_time: datetime
) -> None:
    generator = cls(use_grpc=False)
    sensor = home.get_device(
        next(
            d.device_code
            for d in home.devices
            if d.sensor_type == sensor_type
        )
    )
    payload = generator.generate(home, sensor, fixed_time, sequence=1)
    assert isinstance(payload, dict)
    assert payload


def test_inverter_lifetime_is_monotonic(
    home: Home, fixed_time: datetime
) -> None:
    generator = SolarInverterGenerator(use_grpc=False)
    sensor = home.get_device("INV-T-001-002")
    first = generator.generate(home, sensor, fixed_time, sequence=1)
    second = generator.generate(home, sensor, fixed_time, sequence=2)
    assert (
        second["lifetime_energy_kwh"] >= first["lifetime_energy_kwh"]
    )


def test_battery_soc_in_range(
    home: Home, fixed_time: datetime
) -> None:
    generator = BatteryGenerator(use_grpc=False)
    sensor = home.get_device("BM-T-001-004")
    for _ in range(50):
        payload = generator.generate(home, sensor, fixed_time, sequence=1)
        assert 10.0 <= payload["state_of_charge_pct"] <= 100.0


def test_smart_meter_energy_counters_are_monotonic(
    home: Home, fixed_time: datetime
) -> None:
    generator = SmartMeterGenerator(
        use_grpc=False, interval_seconds=5.0, random_seed=7
    )
    sensor = home.get_device("SM-T-001-001")
    readings = [
        generator.generate(home, sensor, fixed_time, sequence=index)
        for index in range(1, 4)
    ]
    for field in (
        "consumption_energy_kwh",
        "grid_import_energy_kwh",
        "grid_export_energy_kwh",
    ):
        assert [reading[field] for reading in readings] == sorted(
            reading[field] for reading in readings
        )


def test_seeded_generators_are_reproducible(
    home: Home, fixed_time: datetime
) -> None:
    sensor = home.get_device("INV-T-001-002")
    first = SolarInverterGenerator(
        use_grpc=False, interval_seconds=5.0, random_seed=11
    )
    second = SolarInverterGenerator(
        use_grpc=False, interval_seconds=5.0, random_seed=11
    )
    assert first.generate(home, sensor, fixed_time, 1) == second.generate(
        home, sensor, fixed_time, 1
    )


def test_inverter_energy_uses_configured_interval(
    home: Home, fixed_time: datetime
) -> None:
    sensor = home.get_device("INV-T-001-002")
    generator = SolarInverterGenerator(
        use_grpc=False, interval_seconds=3600.0, random_seed=3
    )
    reading = generator.generate(home, sensor, fixed_time, sequence=1)
    assert reading["lifetime_energy_kwh"] == pytest.approx(
        reading["dc_power_w"] / 1000.0, abs=0.001
    )
