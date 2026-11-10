"""Telemetry generator for battery monitors."""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any

import grpc

from generators._random_walk import BoundedWalk
from grpc_client import sensor_pb2
from grpc_client.channel import get_battery_stub
from models.home import Home
from models.sensor import Sensor

logger = logging.getLogger(__name__)


class BatteryGenerator:
    """Produce battery readings with a state-of-charge random walk."""

    def __init__(
        self, use_grpc: bool = True, random_seed: int | None = None
    ) -> None:
        self._use_grpc = use_grpc
        self._random = random.Random(random_seed)
        self._soc = BoundedWalk(
            lo=10.0, hi=100.0, step=2.0, initial=80.0,
            rng=random.Random(self._random.random()),
        )
        self._temperature = BoundedWalk(
            lo=20.0, hi=45.0, step=0.5,
            rng=random.Random(self._random.random()),
        )

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return one battery reading for ``sensor``."""
        capacity_kwh = float(home.battery_capacity_kwh)
        soc = round(self._soc.next(), 2)
        voltage = round(48.0 + soc * 0.06, 2)

        # Simple heuristic: charge when SOC < 50, discharge otherwise.
        if soc < 50.0:
            current = round(self._random.uniform(5, 30), 2)
            charge_power = round(current * voltage, 2)
            discharge_power = 0.0
        else:
            current = round(self._random.uniform(-30, -5), 2)
            charge_power = 0.0
            discharge_power = round(abs(current) * voltage, 2)

        reading = {
            "state_of_charge_pct": soc,
            "battery_voltage_v": voltage,
            "battery_current_a": current,
            "charge_power_w": charge_power,
            "discharge_power_w": discharge_power,
            "temperature_c": round(self._temperature.next(), 2),
            "available_energy_kwh": round(capacity_kwh * soc / 100.0, 2),
        }

        if self._use_grpc:
            request = sensor_pb2.BatteryMonitorSensorRequest(
                device_id=sensor.device_code,
                timestamp=measured_at.isoformat(),
                sequence=sequence,
                home_id=home.home_id,
                measurements=sensor_pb2.BatteryMeasurements(**reading),
                status="OK",
            )
            logger.debug(
                "Preparando envío gRPC para device_id=%s, home_id=%s, sequence=%d",
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
