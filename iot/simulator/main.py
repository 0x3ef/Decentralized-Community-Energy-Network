"""Entry point for the multi-home IoT simulator."""

from __future__ import annotations

import logging
import signal
import time
from contextlib import suppress
from threading import Event

from config.homes import build_default_homes
from config.settings import Settings
from generators import (
    BatteryGenerator,
    SmartMeterGenerator,
    SolarInverterGenerator,
    WeatherGenerator,
)
from generators.base import SensorGenerator
from grpc_client.channel import close_channel
from models.sensor import SensorType
from simulator.coordinator import SimulationConfig, Simulator

logger = logging.getLogger("simulator")


def _install_signal_handlers(stop_event: Event) -> None:
    def _handler(signum: int, _frame: object) -> None:
        logger.info("Received signal %d, shutting down", signum)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            signal.signal(sig, _handler)


def main() -> None:
    """Boot the simulator and block until ``Ctrl+C`` is pressed."""
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    generators: dict[SensorType, SensorGenerator] = {
        SensorType.SMART_METER: SmartMeterGenerator(
            use_grpc=settings.use_grpc,
            interval_seconds=settings.interval_seconds,
            random_seed=settings.random_seed,
        ),
        SensorType.SOLAR_INVERTER: SolarInverterGenerator(
            use_grpc=settings.use_grpc,
            interval_seconds=settings.interval_seconds,
            random_seed=settings.random_seed,
        ),
        SensorType.WEATHER_SENSOR: WeatherGenerator(
            use_grpc=settings.use_grpc, random_seed=settings.random_seed
        ),
        SensorType.BATTERY_MONITOR: BatteryGenerator(
            use_grpc=settings.use_grpc, random_seed=settings.random_seed
        ),
    }

    simulator = Simulator(
        homes=build_default_homes(),
        generators=generators,
        publisher=None,  # The gateway owns MQTT delivery.
        config=SimulationConfig(
            interval_seconds=settings.interval_seconds,
            # A fresh process must not replay low sequence numbers because
            # the backend intentionally deduplicates by device and sequence.
            sequence_offset=(
                settings.sequence_offset
                if settings.sequence_offset is not None
                else int(time.time())
            ),
        ),
    )

    stop_event = Event()
    _install_signal_handlers(stop_event)

    try:
        simulator.run(stop_event=stop_event)
    finally:
        close_channel()

    print("Shutting down multi-home IoT simulator...")

if __name__ == "__main__":
    print("Starting multi-home IoT simulator...")
    main()
