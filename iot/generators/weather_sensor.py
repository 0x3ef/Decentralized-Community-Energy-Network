"""Telemetry generator for weather stations."""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime
from math import pi, sin
from typing import Any

import grpc

from generators._random_walk import BoundedWalk
from grpc_client import sensor_pb2
from grpc_client.channel import get_weather_stub
from models.home import Home
from models.sensor import Sensor

logger = logging.getLogger(__name__)


class WeatherGenerator:
    """Produce weather readings with a realistic diurnal cycle."""

    def __init__(
        self, use_grpc: bool = True, random_seed: int | None = None
    ) -> None:
        self._use_grpc = use_grpc
        rng = random.Random(random_seed)
        self._temperature = BoundedWalk(
            lo=15.0, hi=35.0, step=0.5,
            rng=random.Random(rng.random()),
        )
        self._humidity = BoundedWalk(
            lo=40.0, hi=95.0, step=1.0,
            rng=random.Random(rng.random()),
        )
        self._wind = BoundedWalk(
            lo=0.0, hi=15.0, step=0.5,
            rng=random.Random(rng.random()),
        )

    def generate(
        self,
        home: Home,
        sensor: Sensor,
        measured_at: datetime,
        sequence: int,
    ) -> dict[str, Any]:
        """Return one weather reading for ``sensor``."""
        # Irradiance follows a sine wave peaking at noon.
        local_hour = measured_at.astimezone(
            UTC
        ).hour + measured_at.minute / 60.0
        solar_angle = max(0.0, sin((local_hour - 6) / 12 * pi))
        irradiance = round(1000.0 * solar_angle, 2)

        ambient = round(self._temperature.next(), 2)
        # Panel temperature rises with irradiance.
        panel = round(ambient + irradiance * 0.02, 2)

        reading = {
            "irradiance_w_m2": irradiance,
            "ambient_temperature_c": ambient,
            "panel_temperature_c": panel,
            "relative_humidity_pct": round(self._humidity.next(), 2),
            "wind_speed_m_s": round(self._wind.next(), 2),
        }

        if self._use_grpc:
            request = sensor_pb2.WeatherSensorRequest(
                device_id=sensor.device_code,
                timestamp=measured_at.isoformat(),
                sequence=sequence,
                home_id=home.home_id,
                measurements=sensor_pb2.WeatherMeasurements(**reading),
            )
            try:
                get_weather_stub().SendWeatherRequest(request, timeout=5.0)
            except grpc.RpcError as exc:
                logger.warning(
                    "Weather gRPC failed (%s: %s)",
                    exc.code(),
                    exc.details(),
                )

        return reading
