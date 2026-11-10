"""Tests for the home catalogue."""

from __future__ import annotations

from decimal import Decimal

from config.homes import build_default_homes, build_home
from models.sensor import SensorType


def test_build_home_skips_battery_when_zero() -> None:
    home = build_home("HOME-A-001", "City", solar_kw=3.0, battery_kwh=0.0)
    types = {sensor.sensor_type for sensor in home.devices}
    assert SensorType.BATTERY_MONITOR not in types


def test_build_home_with_battery() -> None:
    home = build_home("HOME-A-001", "City", solar_kw=3.0, battery_kwh=5.0)
    types = {sensor.sensor_type for sensor in home.devices}
    assert SensorType.BATTERY_MONITOR in types


def test_default_homes_have_unique_ids() -> None:
    homes = build_default_homes()
    ids = [home.home_id for home in homes]
    assert len(ids) == len(set(ids))


def test_build_home_uses_decimal() -> None:
    home = build_home("HOME-A-001", "City", solar_kw=4.5, battery_kwh=1.0)
    assert isinstance(home.solar_capacity_kw, Decimal)
