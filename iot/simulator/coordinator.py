"""Coordinate multiple homes and their IoT devices."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Any

from generators.base import SensorGenerator
from models.home import Home
from models.sensor import Sensor, SensorType
from publishers.base import TelemetryPublisher

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Configuration for the simulation loop.

    Args:
        interval_seconds: Delay between cycles. Must be > 0.

    Raises:
        ValueError: If ``interval_seconds`` is not strictly positive.
    """

    interval_seconds: float = 15.0
    sequence_offset: int = 0
    random_seed: int | None = None
    checkpoint_path: str | None = None
    telemetry_version: str = "2.0"
    mode: str = "REALTIME"
    speed: float = 1
    start: datetime | None = None
    fault: str = "none"
    fault_device: str | None = None
    accounting_interval_seconds: int = 900

    def __post_init__(self) -> None:
        if self.fault not in (
            "none",
            "outage",
            "device_outage",
            "duplicate",
            "packet_loss",
            "out_of_order",
            "counter_reset",
            "clock_drift",
            "invalid_payload",
            "power_spike",
            "export_spike",
            "delay",
            "mqtt_disconnection",
            "unauthorized_device",
            "missing_interval",
        ):
            raise ValueError("Unknown deterministic fault")
        if self.speed <= 0:
            raise ValueError("Simulation speed must be positive")
        if self.mode not in (
            "REALTIME",
            "ACCELERATED",
            "DETERMINISTIC",
        ) or self.telemetry_version not in ("1.0", "2.0"):
            raise ValueError("Invalid simulation mode or telemetry version")
        if self.mode == "REALTIME" and (
            self.speed != 1 or self.start is not None or self.fault != "none"
        ):
            raise ValueError("Acceleration and faults require explicit offline mode")
        if self.mode != "REALTIME" and (
            self.start is None or self.telemetry_version != "2.0"
        ):
            raise ValueError("Offline mode requires explicit start and v2 provenance")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if self.accounting_interval_seconds <= 0:
            raise ValueError("accounting_interval_seconds must be greater than zero")
        if self.sequence_offset < 0:
            raise ValueError("sequence_offset cannot be negative")


class Simulator:
    """Drive simulation cycles across every active device.

    The simulator does **not** publish telemetry by itself: it forwards
    the payload to the publisher passed in the constructor, if any. In
    the gateway-based architecture, ``publisher`` is ``None`` and the
    gateway handles MQTT delivery.
    """

    def __init__(
        self,
        homes: Iterable[Home],
        generators: dict[SensorType, SensorGenerator],
        publisher: TelemetryPublisher | None = None,
        config: SimulationConfig | None = None,
        profiles: dict | None = None,
    ) -> None:
        self._homes = tuple(homes)
        self._generators = generators
        self._publisher = publisher
        self._config = config or SimulationConfig()
        self._sequence_numbers: dict[str, int] = {}
        self._sequence_offset = self._config.sequence_offset
        from simulator.clock import DeterministicClock, SimulationClock

        self._clock = (
            DeterministicClock(
                self._config.start, self._config.interval_seconds * self._config.speed
            )
            if self._config.mode == "DETERMINISTIC"
            else SimulationClock(
                self._config.start,
                self._config.speed,
                offline=self._config.mode != "REALTIME",
            )
        )
        from uuid import NAMESPACE_URL, uuid4, uuid5

        self._session_id = (
            uuid5(
                NAMESPACE_URL,
                f"simulation:{self._config.random_seed}:{self._config.start}",
            )
            if self._config.mode == "DETERMINISTIC"
            else uuid4()
        )
        self._validate_configuration()
        import hashlib

        from simulator.physics import HomeEnergyModel

        shared = {
            home.home_id: HomeEnergyModel(
                home,
                profile=(profiles or {}).get(home.home_id),
                seed=int.from_bytes(
                    hashlib.sha256(
                        f"{self._config.random_seed}:{home.home_id}".encode()
                    ).digest()[:8],
                    "big",
                ),
            )
            for home in self._homes
        }
        self._pending: dict[str, dict] = {}
        self._fault_delayed = {}
        self._energy_models = shared
        if self._config.checkpoint_path:
            from simulator.checkpoint import load

            load(
                self._config.checkpoint_path,
                self._sequence_numbers,
                shared,
                self._pending,
            )
        for generator in self._generators.values():
            generator._energy_models = shared

    def _validate_configuration(self) -> None:
        """Validate homes, devices and generator registrations."""
        home_ids = [home.home_id for home in self._homes]
        if len(home_ids) != len(set(home_ids)):
            raise ValueError("Duplicate home IDs detected")

        device_codes: set[str] = set()
        for home in self._homes:
            for sensor in home.devices:
                if sensor.home_id != home.home_id:
                    raise ValueError(
                        f"Device {sensor.device_code} belongs to "
                        f"{sensor.home_id}, not {home.home_id}"
                    )
                if sensor.device_code in device_codes:
                    raise ValueError(f"Duplicate device code: {sensor.device_code}")
                device_codes.add(sensor.device_code)
                if sensor.sensor_type not in self._generators:
                    raise ValueError(
                        f"No generator registered for {sensor.sensor_type}"
                    )
                self._sequence_numbers[sensor.device_code] = self._sequence_offset

    def simulate_sensor(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
    ) -> dict[str, Any] | None:
        """Generate one telemetry message for ``sensor``."""
        if not sensor.is_active:
            logger.debug("Skipping inactive device %s", sensor.device_code)
            return None

        next_sequence = self._sequence_numbers[sensor.device_code] + 1
        self._sequence_numbers[sensor.device_code] = next_sequence

        generator = self._generators[sensor.sensor_type]
        data = generator.generate(
            home=home,
            sensor=sensor,
            measured_at=measured_at,
            sequence=next_sequence,
        )

        message = {
            "schema_version": self._config.telemetry_version,
            "home_id": home.home_id,
            "device_id": sensor.device_code,
            "sensor_type": sensor.sensor_type.value,
            "sequence_number": next_sequence,
            "measured_at": measured_at.isoformat(),
            "data": data,
        }

        if self._config.telemetry_version == "2.0":
            from uuid import uuid5

            from schemas.telemetry import measurement_unit

            message.update(
                message_id=str(
                    uuid5(
                        self._session_id,
                        f"{sensor.device_code}:{next_sequence}:{measured_at.isoformat()}",
                    )
                ),
                community_id="unregistered",
                node_id=home.home_id,
                source="SIMULATED",
                simulation_mode=self._config.mode,
                units={field: measurement_unit(field) for field in data},
                quality=["VALID"],
            )
        return message

    def simulate_cycle(
        self, measured_at: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Run one cycle over every active device."""
        measured_at = measured_at or self._clock.now()
        if measured_at.tzinfo is None:
            raise ValueError("Simulation timestamps must be timezone-aware")
        measured_at = measured_at.astimezone(UTC)
        messages: list[dict[str, Any]] = []

        for home in self._homes:
            for sensor in home.devices:
                try:
                    if sensor.device_code in self._pending:
                        message = self._pending[sensor.device_code]
                        self._publisher.publish(sensor.get_mqtt_topic(), message)
                        del self._pending[sensor.device_code]
                        messages.append(message)
                        continue
                    message = self.simulate_sensor(
                        home=home,
                        sensor=sensor,
                        measured_at=measured_at,
                    )
                    if message is None:
                        continue

                    from simulator.faults import inject

                    fault = (
                        self._config.fault
                        if self._config.fault_device in (None, sensor.device_code)
                        else "none"
                    )
                    if fault == "out_of_order":
                        old = self._fault_delayed.pop(sensor.device_code, None)
                        if old is None:
                            self._fault_delayed[sensor.device_code] = message
                            continue
                        emitted = [message, old]
                    else:
                        emitted = inject([message], fault)
                    if fault == "mqtt_disconnection":
                        raise ConnectionError("Injected MQTT disconnect")
                    if not emitted:
                        continue
                    message = emitted[0]
                    if self._publisher is not None:
                        self._pending[sensor.device_code] = message
                        self._publisher.publish(sensor.get_mqtt_topic(), message)
                        del self._pending[sensor.device_code]

                    messages.append(message)
                    for duplicate in emitted[1:]:
                        if self._publisher is not None:
                            self._publisher.publish(sensor.get_mqtt_topic(), duplicate)
                        messages.append(duplicate)
                    logger.info(
                        "Generated telemetry: home=%s device=%s seq=%d",
                        home.home_id,
                        sensor.device_code,
                        message["sequence_number"],
                    )
                except Exception:
                    logger.exception(
                        "Failed to simulate device %s",
                        sensor.device_code,
                    )

        if self._config.checkpoint_path:
            from simulator.checkpoint import save

            save(
                self._config.checkpoint_path,
                self._sequence_numbers,
                self._energy_models,
                self._pending,
            )
        return messages

    def run(self, stop_event: Event | None = None) -> None:
        """Run simulation cycles until ``stop_event`` is set."""
        stop_event = stop_event or Event()
        logger.info("Starting simulation with %d homes", len(self._homes))

        if self._config.mode == "REALTIME":
            from simulator.clock import next_sample_at

            step = self._config.interval_seconds
            boundary = self._config.accounting_interval_seconds
            while not stop_event.is_set():
                target = next_sample_at(self._clock.now(), step, boundary)
                # Wait for the observation time; don't publish future readings.
                while not stop_event.is_set():
                    now = self._clock.now()
                    remaining = (target - now).total_seconds()
                    if remaining <= 0:
                        break
                    stop_event.wait(remaining)
                if stop_event.is_set():
                    break
                if (now - target).total_seconds() >= min(step, boundary):
                    logger.warning("Missed sampling slot %s; no backfill", target)
                    continue
                self.simulate_cycle(target)
            logger.info("Simulation stopped")
            return

        while not stop_event.is_set():
            cycle_started = time.monotonic()
            self.simulate_cycle()

            elapsed = time.monotonic() - cycle_started
            remaining = max(0.0, self._config.interval_seconds - elapsed)
            stop_event.wait(remaining)

        logger.info("Simulation stopped")
