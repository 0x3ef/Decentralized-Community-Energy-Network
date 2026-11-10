"""Sensor observations must reflect elapsed time and independent physical state."""

from datetime import datetime, UTC, timedelta
from decimal import Decimal
import pytest
from config.homes import build_home
from generators import (
    BatteryGenerator,
    SmartMeterGenerator,
    SolarInverterGenerator,
    WeatherGenerator,
)
from models.sensor import SensorType

CASES = [
    (SmartMeterGenerator, SensorType.SMART_METER),
    (SolarInverterGenerator, SensorType.SOLAR_INVERTER),
    (WeatherGenerator, SensorType.WEATHER_SENSOR),
    (BatteryGenerator, SensorType.BATTERY_MONITOR),
]


def sensor_for(home, kind):
    return next(device for device in home.devices if device.sensor_type == kind)


@pytest.mark.parametrize("factory,kind", CASES)
def test_seeded_observations_are_reproducible_over_elapsed_steps(factory, kind):
    home = build_home("HOME-CALI-001", "Cali", 5, 10)
    sensor = sensor_for(home, kind)
    left = factory(use_grpc=False, random_seed=17)
    right = factory(use_grpc=False, random_seed=17)
    start = datetime(2026, 6, 21, 17, tzinfo=UTC)
    for seq, seconds in enumerate((0, 13, 47, 120), start=1):
        at = start + timedelta(seconds=seconds)
        assert left.generate(home, sensor, at, seq) == right.generate(
            home, sensor, at, seq
        )


def test_meter_counters_integrate_observed_power_not_configured_scheduler_delay():
    home = build_home("HOME-CALI-001", "Cali", 0, 0)
    sensor = sensor_for(home, SensorType.SMART_METER)
    meter = SmartMeterGenerator(use_grpc=False, interval_seconds=3600, random_seed=7)
    start = datetime(2026, 6, 21, 17, tzinfo=UTC)
    baseline = meter.generate(home, sensor, start, 1)
    assert baseline["consumption_energy_kwh"] == baseline["grid_import_energy_kwh"] == 0
    reading = meter.generate(home, sensor, start + timedelta(seconds=37), 2)
    assert reading["grid_export_energy_kwh"] == 0
    assert reading["grid_import_energy_kwh"] == reading["consumption_energy_kwh"] > 0
    expected = reading["active_power_w"] * Decimal(37) / Decimal(3600000)
    assert abs(reading["consumption_energy_kwh"] - expected) < Decimal(".000000001")
    assert meter.generate(home, sensor, start + timedelta(seconds=37), 3) == reading


def test_shared_generator_does_not_share_counters_between_homes():
    first = build_home("HOME-CALI-001", "Cali", 0, 0)
    second = build_home("HOME-CALI-002", "Cali", 0, 0)
    meter = SmartMeterGenerator(False, random_seed=8)
    start = datetime(2026, 6, 21, 17, tzinfo=UTC)
    meter.generate(first, sensor_for(first, SensorType.SMART_METER), start, 1)
    meter.generate(
        first,
        sensor_for(first, SensorType.SMART_METER),
        start + timedelta(minutes=10),
        2,
    )
    other = meter.generate(
        second,
        sensor_for(second, SensorType.SMART_METER),
        start + timedelta(minutes=10),
        1,
    )
    assert other["consumption_energy_kwh"] == 0


def test_inverter_energy_uses_ac_output_and_actual_elapsed_time():
    home = build_home("HOME-CALI-001", "Cali", 5, 0)
    sensor = sensor_for(home, SensorType.SOLAR_INVERTER)
    inverter = SolarInverterGenerator(False, interval_seconds=3600, random_seed=3)
    start = datetime(2026, 6, 21, 17, tzinfo=UTC)
    assert inverter.generate(home, sensor, start, 1)["lifetime_energy_kwh"] == 0
    reading = inverter.generate(home, sensor, start + timedelta(seconds=30), 2)
    assert abs(
        reading["lifetime_energy_kwh"] - reading["ac_power_w"] * Decimal(30) / 3600000
    ) < Decimal(".000000001")
    assert reading["ac_power_w"] <= reading["dc_power_w"]


def test_battery_limits_hold_over_a_full_day_not_repeated_identical_timestamps():
    home = build_home("HOME-CALI-001", "Cali", 5, 10)
    sensor = sensor_for(home, SensorType.BATTERY_MONITOR)
    generator = BatteryGenerator(False, random_seed=4)
    start = datetime(2026, 6, 21, tzinfo=UTC)
    seen = set()
    for minute in range(0, 1440, 5):
        reading = generator.generate(
            home, sensor, start + timedelta(minutes=minute), minute + 1
        )
        assert 9.999 <= reading["state_of_charge_pct"] <= 95.001
        assert not (reading["charge_power_w"] and reading["discharge_power_w"])
        seen.add(round(reading["state_of_charge_pct"], 2))
    assert len(seen) > 1


@pytest.mark.parametrize("factory", [SmartMeterGenerator, SolarInverterGenerator])
def test_invalid_scheduler_interval_rejected(factory):
    with pytest.raises(ValueError):
        factory(use_grpc=False, interval_seconds=0)
