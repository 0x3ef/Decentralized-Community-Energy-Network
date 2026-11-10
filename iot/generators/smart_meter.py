"""Telemetry generator for smart meters."""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime
from typing import Any

import grpc

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
        self._seed = random_seed
        self._use_grpc = use_grpc

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return one smart-meter reading for ``sensor``."""
        from simulator.physics import HomeEnergyModel

        if not hasattr(self, "_energy_models"):
            self._energy_models = {}
        if home.home_id not in self._energy_models:
            self._energy_models[home.home_id] = HomeEnergyModel(
                home, seed=getattr(self, "_seed", None)
            )
        reading = self._energy_models[home.home_id].reading("smart_meter", measured_at)
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
            measurements=sensor_pb2.SmartMeterMeasurements(
                **{
                    k: float(v) if isinstance(v, Decimal) else v
                    for k, v in reading.items()
                    if k in sensor_pb2.SmartMeterMeasurements.DESCRIPTOR.fields_by_name
                }
            ),
        )
        try:
            get_smart_meter_stub().SendSmartMeterRequest(request, timeout=5.0)
        except grpc.RpcError as exc:
            logger.warning(
                "Smart meter gRPC failed (%s: %s)",
                exc.code(),
                exc.details(),
            )
