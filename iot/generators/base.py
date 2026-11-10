"""Common contract for all telemetry generators."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from models.home import Home
from models.sensor import Sensor


class SensorGenerator(Protocol):
    """Interface implemented by every sensor data generator.

    Each call to :meth:`generate` must produce exactly **one**
    telemetry payload. The scheduling loop lives in
    :class:`simulator.coordinator.Simulator`.
    """

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return a telemetry payload for ``sensor``.

        Args:
            home: Home that owns the device.
            sensor: Device that produced the measurement.
            measured_at: UTC timestamp assigned by the coordinator.
            sequence: Monotonic per-device sequence number.

        Returns:
            A JSON-serialisable dictionary with the sensor readings.
        """
        ...
