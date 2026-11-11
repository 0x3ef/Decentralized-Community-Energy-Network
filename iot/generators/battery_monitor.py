"""Telemetry generator for battery monitors."""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime
from typing import Any

import grpc

from grpc_client import sensor_pb2
from grpc_client.channel import get_battery_stub
from models.home import Home
from models.sensor import Sensor

logger = logging.getLogger(__name__)


class BatteryGenerator:
    """Produce battery readings with a state-of-charge random walk."""

    def __init__(self, use_grpc: bool = True, random_seed: int | None = None) -> None:
        self._seed = random_seed
        self._use_grpc = use_grpc

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return one battery reading for ``sensor``."""
        from simulator.physics import HomeEnergyModel

        if not hasattr(self, "_energy_models"):
            self._energy_models = {}
        if home.home_id not in self._energy_models:
            self._energy_models[home.home_id] = HomeEnergyModel(
                home, seed=getattr(self, "_seed", None)
            )
        reading = self._energy_models[home.home_id].reading(
            "battery_monitor", measured_at
        )
        if self._use_grpc:
            request = sensor_pb2.BatteryMonitorSensorRequest(
                device_id=sensor.device_code,
                timestamp=measured_at.isoformat(),
                sequence=sequence,
                home_id=home.home_id,
                measurements=sensor_pb2.BatteryMeasurements(
                    **{
                        k: float(v) if isinstance(v, Decimal) else v
                        for k, v in reading.items()
                        if k in sensor_pb2.BatteryMeasurements.DESCRIPTOR.fields_by_name
                    }
                ),
                status="OK",
            )
            logger.debug(
                "Preparing gRPC delivery for device_id=%s, home_id=%s, sequence=%d",
                sensor.device_code,
                home.home_id,
                sequence,
            )

            try:
                stub = get_battery_stub()
                stub.SendBatteryMonitorRequest(request, timeout=5.0)
            except grpc.RpcError as exc:
                logger.warning(
                    "Battery gRPC failed (%s: %s)",
                    exc.code(),
                    exc.details(),
                )

        return {**reading, "status": "OK"}
