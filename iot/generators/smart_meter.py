"""Telemetry generator for smart meters."""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any

import grpc

from generators._random_walk import BoundedWalk
from grpc_client import sensor_pb2
from grpc_client.channel import get_smart_meter_stub
from models.home import Home
from models.sensor import Sensor

logger = logging.getLogger(__name__)


class SmartMeterGenerator:
    """Produce smart meter readings, optionally forwarded over gRPC."""

    def __init__(
        self,
        use_grpc: bool = True,
        interval_seconds: float = 15.0,
        random_seed: int | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self._use_grpc = use_grpc
        self._interval_seconds = interval_seconds
        rng = random.Random(random_seed)
        self._voltage = BoundedWalk(
            lo=110.0, hi=130.0, step=1.0, rng=random.Random(rng.random())
        )
        self._frequency = BoundedWalk(
            lo=59.5, hi=60.5, step=0.05, rng=random.Random(rng.random())
        )
        self._power_factor = BoundedWalk(
            lo=0.85, hi=1.0, step=0.02, rng=random.Random(rng.random())
        )
        # Negative net power represents export to the grid. This lets the
        # simulator exercise both import and surplus-energy workflows.
        self._active_power = BoundedWalk(
            lo=-3000.0, hi=5000.0, step=400.0, initial=800.0,
            rng=random.Random(rng.random()),
        )
        self._consumption_power = BoundedWalk(
            lo=250.0, hi=4500.0, step=200.0, initial=1200.0,
            rng=random.Random(rng.random()),
        )
        self._consumption_energy_kwh = 0.0
        self._grid_import_energy_kwh = 0.0
        self._grid_export_energy_kwh = 0.0

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return one smart-meter reading for ``sensor``."""
        active_power = round(self._active_power.next(), 2)
        consumption_power = self._consumption_power.next()
        interval_hours = self._interval_seconds / 3600.0
        import_power = max(active_power, 0.0)
        export_power = max(-active_power, 0.0)
        self._consumption_energy_kwh += (
            consumption_power * interval_hours / 1000.0
        )
        self._grid_import_energy_kwh += (
            import_power * interval_hours / 1000.0
        )
        self._grid_export_energy_kwh += (
            export_power * interval_hours / 1000.0
        )

        reading = {
            "voltage_v": round(self._voltage.next(), 2),
            # Current is reported as a non-negative magnitude; direction is
            # represented by signed active power and import/export fields.
            "current_a": round(abs(active_power) / 120.0, 2),
            "frequency_hz": round(self._frequency.next(), 2),
            "active_power_w": active_power,
            "power_factor": round(self._power_factor.next(), 3),
            "grid_import_power_w": round(import_power, 2),
            "grid_export_power_w": round(export_power, 2),
            "consumption_energy_kwh": round(self._consumption_energy_kwh, 3),
            "grid_import_energy_kwh": round(
                self._grid_import_energy_kwh, 3
            ),
            "grid_export_energy_kwh": round(
                self._grid_export_energy_kwh, 3
            ),
        }

        if self._use_grpc:
            self._send_via_grpc(home, sensor, measured_at, sequence, reading)

        return reading

    def _send_via_grpc(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
        reading: dict[str, Any],
    ) -> None:
        request = sensor_pb2.SmartMeterSensorRequest(
            device_id=sensor.device_code,
            timestamp=measured_at.isoformat(),
            sequence=sequence,
            home_id=home.home_id,
            measurements=sensor_pb2.SmartMeterMeasurements(**reading),
        )
        try:
            get_smart_meter_stub().SendSmartMeterRequest(request, timeout=5.0)
        except grpc.RpcError as exc:
            logger.warning(
                "Smart meter gRPC failed (%s: %s)",
                exc.code(),
                exc.details(),
            )
