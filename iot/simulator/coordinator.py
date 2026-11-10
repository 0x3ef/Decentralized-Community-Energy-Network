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

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError(
                "interval_seconds must be greater than zero"
            )
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
    ) -> None:
        self._homes = tuple(homes)
        self._generators = generators
        self._publisher = publisher
        self._config = config or SimulationConfig()
        self._sequence_numbers: dict[str, int] = {}
        self._sequence_offset = self._config.sequence_offset
        self._validate_configuration()

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
                    raise ValueError(
                        f"Duplicate device code: {sensor.device_code}"
                    )
                device_codes.add(sensor.device_code)
                if sensor.sensor_type not in self._generators:
                    raise ValueError(
                        f"No generator registered for "
                        f"{sensor.sensor_type}"
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
            logger.debug(
                "Skipping inactive device %s", sensor.device_code
            )
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

        return {
            "schema_version": "1.0",
            "home_id": home.home_id,
            "device_id": sensor.device_code,
            "sensor_type": sensor.sensor_type.value,
            "sequence_number": next_sequence,
            "measured_at": measured_at.isoformat(),
            "data": data,
        }

    def simulate_cycle(self) -> list[dict[str, Any]]:
        """Run one cycle over every active device."""
        measured_at = datetime.now(UTC)
        messages: list[dict[str, Any]] = []

        for home in self._homes:
            for sensor in home.devices:
                try:
                    message = self.simulate_sensor(
                        home=home, sensor=sensor, measured_at=measured_at,
                    )
                    if message is None:
                        continue

                    if self._publisher is not None:
                        self._publisher.publish(
                            sensor.get_mqtt_topic(), message
                        )

                    messages.append(message)
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

        return messages

    def run(self, stop_event: Event | None = None) -> None:
        """Run simulation cycles until ``stop_event`` is set."""
        stop_event = stop_event or Event()
        logger.info("Starting simulation with %d homes", len(self._homes))

        while not stop_event.is_set():
            cycle_started = time.monotonic()
            self.simulate_cycle()

            elapsed = time.monotonic() - cycle_started
            remaining = max(0.0, self._config.interval_seconds - elapsed)
            stop_event.wait(remaining)

        logger.info("Simulation stopped")
