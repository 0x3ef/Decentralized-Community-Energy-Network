"""Telemetry generator for solar inverters."""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any

import grpc

from generators._random_walk import BoundedWalk
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
        self._use_grpc = use_grpc
        self._interval_seconds = interval_seconds
        self._random = random.Random(random_seed)
        self._lifetime_kwh: dict[str, float] = {}
        self._efficiency = BoundedWalk(
            lo=85.0, hi=99.0, step=0.5,
            rng=random.Random(self._random.random()),
        )
        self._temperature = BoundedWalk(
            lo=25.0, hi=75.0, step=1.5,
            rng=random.Random(self._random.random()),
        )

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return one inverter reading for ``sensor``."""
        capacity_kw = float(home.solar_capacity_kw)
        dc_power = round(
            self._random.uniform(0, capacity_kw * 1000), 2
        )
        efficiency = round(self._efficiency.next(), 2)
        ac_power = round(dc_power * efficiency / 100.0, 2)

        lifetime = self._lifetime_kwh.get(sensor.device_code, 0.0)
        lifetime += (
            dc_power * (self._interval_seconds / 3600.0) / 1000.0
        )
        self._lifetime_kwh[sensor.device_code] = lifetime

        reading = {
            "dc_power_w": dc_power,
            "ac_power_w": ac_power,
            "daily_energy_kwh": round(lifetime % 30.0, 3),
            "lifetime_energy_kwh": round(lifetime, 3),
            "temperature_c": round(self._temperature.next(), 2),
            "efficiency_pct": efficiency,
        }

        if self._use_grpc:
            self._send_via_grpc(
                home, sensor, measured_at, sequence, reading
            )

        return {
            **reading,
            "operating_state": True,
            "alarm_code": "",
        }

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
            measurements=sensor_pb2.SolarInverterMeasurements(**reading),
            status=sensor_pb2.SolarInverterStatus(
                operating_state=True, alarm_code=""
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
