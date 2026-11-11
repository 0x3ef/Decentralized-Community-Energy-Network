"""Tests for the SimulationCoordinator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def test_duplicate_homes_rejected(sample_home: Home, generators) -> None:
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


def test_sequence_numbers_increase(sample_home: Home, generators) -> None:
    simulator = Simulator(homes=[sample_home], generators=generators)
    simulator.simulate_cycle()
    messages = simulator.simulate_cycle()
    assert all(m["sequence_number"] == 2 for m in messages)


def test_sequence_offset_prevents_replay(sample_home: Home, generators) -> None:
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


def test_failed_publish_retries_original_sequence_before_new_measurements(
    sample_home, generators
):
    class Unreliable:
        fail = True

        def publish(self, topic, message):
            if self.fail:
                raise ConnectionError("broker unavailable")

        def close(self):
            pass

    publisher = Unreliable()
    simulator = Simulator([sample_home], generators, publisher)
    assert simulator.simulate_cycle() == []
    pending = {
        code: message["sequence_number"] for code, message in simulator._pending.items()
    }
    publisher.fail = False
    recovered = simulator.simulate_cycle()
    assert recovered and not simulator._pending
    assert all(
        message["sequence_number"] == pending[message["device_id"]]
        for message in recovered
    )


class WallTime:
    def __init__(self, at):
        self.at = at

    def now(self):
        return self.at


class AdvancingStop:
    """Advance simulated wall time instead of sleeping in scheduler tests."""

    def __init__(self, clock, end, stall=0):
        self.clock, self.end, self.stall = clock, end, stall

    def is_set(self):
        return self.clock.at > self.end

    def wait(self, seconds):
        self.clock.at += timedelta(seconds=seconds + self.stall)
        self.stall = 0


def test_realtime_waits_for_utc_slots_and_observes_both_interval_boundaries(
    sample_home, generators
):
    start = datetime(2026, 11, 11, 17, 0, tzinfo=UTC)
    clock = WallTime(start - timedelta(seconds=4, microseconds=137))
    simulator = Simulator([sample_home], generators)
    simulator._clock = clock
    messages = []
    simulate_cycle = simulator.simulate_cycle

    def record(at):
        assert at <= clock.now()  # no future-dated observations
        messages.extend(simulate_cycle(at))

    simulator.simulate_cycle = record
    simulator.run(AdvancingStop(clock, start + timedelta(minutes=15)))
    times = {datetime.fromisoformat(m["measured_at"]) for m in messages}
    assert len(times) == 61
    assert min(times) == start and max(times) == start + timedelta(minutes=15)
    assert all(t.microsecond == 0 and t.second % 15 == 0 for t in times)
    by_device = [m for m in messages if m["sensor_type"] == "smart_meter"]
    assert [m["sequence_number"] for m in by_device] == list(range(1, 62))


def test_realtime_stall_does_not_backfill_missing_boundary(sample_home, generators):
    boundary = datetime(2026, 11, 11, 17, 15, tzinfo=UTC)
    clock = WallTime(boundary - timedelta(seconds=1))
    simulator = Simulator([sample_home], generators)
    simulator._clock = clock
    observed = []
    simulator.simulate_cycle = observed.append
    simulator.run(AdvancingStop(clock, boundary + timedelta(seconds=45), stall=20))
    assert observed == [
        boundary + timedelta(seconds=30),
        boundary + timedelta(seconds=45),
    ]


def test_utc_scheduler_includes_boundaries_for_non_dividing_cadence():
    from simulator.clock import next_sample_at

    boundary = datetime(2026, 11, 11, 17, 15, tzinfo=UTC)
    at = boundary - timedelta(seconds=8)
    seen = []
    while at < boundary:
        at = next_sample_at(at, 7)
        seen.append(at)
    assert seen[-1] == boundary
    assert next_sample_at(boundary, 7) > boundary
