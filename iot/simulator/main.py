"""Entry point for the multi-home IoT simulator."""

from __future__ import annotations

import logging
from decimal import Decimal
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

    publisher = None
    if not settings.use_grpc:
        if settings.device_registry:
            from publishers.registered import RegisteredPublisher
            from publishers.mqtt_publisher import MqttPublisher

            publisher = RegisteredPublisher(
                MqttPublisher(
                    settings.mqtt_host,
                    settings.mqtt_port,
                    client_id="solar-registered-simulator",
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                    tls=settings.mqtt_tls,
                    ca_cert=settings.mqtt_ca_cert,
                    client_cert=settings.mqtt_client_cert,
                    client_key=settings.mqtt_client_key,
                ),
                settings.device_registry,
            )
        else:
            from publishers.console_publisher import ConsolePublisher

            publisher = ConsolePublisher()
    import json
    from simulator.physics import HomeProfile

    profiles = {
        key: HomeProfile(
            **{
                k: Decimal(str(v))
                if k not in ("latitude", "longitude", "timezone")
                else v
                for k, v in value.items()
            }
        )
        for key, value in json.loads(settings.home_profiles_json).items()
    }
    simulator = Simulator(
        profiles=profiles,
        homes=build_default_homes(),
        generators=generators,
        publisher=publisher,
        config=SimulationConfig(
            interval_seconds=settings.interval_seconds,
            random_seed=settings.random_seed,
            checkpoint_path=settings.checkpoint_path,
            # A fresh process must not replay low sequence numbers because
            # the backend intentionally deduplicates by device and sequence.
            sequence_offset=(
                settings.sequence_offset
                if settings.sequence_offset is not None
                else int(time.time() * 1000)
            ),
        ),
    )

    stop_event = Event()
    _install_signal_handlers(stop_event)

    try:
        simulator.run(stop_event=stop_event)
    finally:
        close_channel()
        if publisher is not None:
            publisher.close()

    print("Shutting down multi-home IoT simulator...")


if __name__ == "__main__":
    print("Starting multi-home IoT simulator...")
    main()
