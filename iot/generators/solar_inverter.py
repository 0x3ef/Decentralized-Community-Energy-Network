"""Telemetry generator for solar inverters."""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime
from typing import Any

import grpc

from grpc_client import sensor_pb2
from grpc_client.channel import get_solar_inverter_stub
from models.home import Home
from models.sensor import Sensor

logger = logging.getLogger(__name__)


class SolarInverterGenerator:
    """Produce inverter readings with accumulated lifetime energy."""

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
        """Return one inverter reading for ``sensor``."""
        from simulator.physics import HomeEnergyModel

        if not hasattr(self, "_energy_models"):
            self._energy_models = {}
        if home.home_id not in self._energy_models:
            self._energy_models[home.home_id] = HomeEnergyModel(
                home, seed=getattr(self, "_seed", None)
            )
        reading = self._energy_models[home.home_id].reading(
            "solar_inverter", measured_at
        )
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
        request = sensor_pb2.SolarInverterSensorRequest(
            device_id=sensor.device_code,
            timestamp=measured_at.isoformat(),
            sequence=sequence,
            home_id=home.home_id,
            measurements=sensor_pb2.SolarInverterMeasurements(
                **{
                    k: float(v) if isinstance(v, Decimal) else v
                    for k, v in reading.items()
                    if k not in ("operating_state", "alarm_code")
                }
            ),
            status=sensor_pb2.SolarInverterStatus(
                operating_state=bool(reading["operating_state"]), alarm_code=""
            ),
        )
        try:
            get_solar_inverter_stub().SendSolarInverterRequest(request, timeout=5.0)
        except grpc.RpcError as exc:
            logger.warning(
                "Inverter gRPC failed (%s: %s)",
                exc.code(),
                exc.details(),
            )
