"""Tests for the SimulationCoordinator."""

from __future__ import annotations

import pytest

from generators import (
    BatteryGenerator,
    SmartMeterGenerator,
    SolarInverterGenerator,
    WeatherGenerator,
)
from models.home import Home
from models.sensor import SensorType
from simulator import SimulationConfig, Simulator


@pytest.fixture()
def generators() -> dict[SensorType, object]:
    return {
        SensorType.SMART_METER: SmartMeterGenerator(use_grpc=False),
        SensorType.SOLAR_INVERTER: SolarInverterGenerator(use_grpc=False),
        SensorType.WEATHER_SENSOR: WeatherGenerator(use_grpc=False),
        SensorType.BATTERY_MONITOR: BatteryGenerator(use_grpc=False),
    }


def test_duplicate_homes_rejected(
    sample_home: Home, generators
) -> None:
    with pytest.raises(ValueError, match="Duplicate home IDs"):
        Simulator(homes=[sample_home, sample_home], generators=generators)


def test_cycle_returns_messages(sample_home: Home, generators) -> None:
    simulator = Simulator(
        homes=[sample_home],
        generators=generators,
        config=SimulationConfig(interval_seconds=1),
    )
    messages = simulator.simulate_cycle()
    assert len(messages) == len(sample_home.devices)
    assert all("sequence_number" in m for m in messages)


def test_sequence_numbers_increase(
    sample_home: Home, generators
) -> None:
    simulator = Simulator(homes=[sample_home], generators=generators)
    simulator.simulate_cycle()
    messages = simulator.simulate_cycle()
    assert all(m["sequence_number"] == 2 for m in messages)


def test_sequence_offset_prevents_replay(
    sample_home: Home, generators
) -> None:
    simulator = Simulator(
        homes=[sample_home],
        generators=generators,
        config=SimulationConfig(sequence_offset=100),
    )
    assert simulator.simulate_cycle()[0]["sequence_number"] == 101


def test_invalid_interval_rejected() -> None:
    with pytest.raises(ValueError):
        SimulationConfig(interval_seconds=0)


def test_publisher_is_called(sample_home: Home, generators) -> None:
    calls: list[tuple[str, dict]] = []

    class FakePublisher:
        def publish(self, topic: str, message: dict) -> None:
            calls.append((topic, message))

        def close(self) -> None:
            pass

    simulator = Simulator(
        homes=[sample_home],
        generators=generators,
        publisher=FakePublisher(),
    )
    simulator.simulate_cycle()
    assert len(calls) == len(sample_home.devices)
    assert calls[0][0].startswith("solar/HOME-TEST-001/")
