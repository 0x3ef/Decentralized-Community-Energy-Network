"""Entry point for the multi-home IoT simulator."""

from __future__ import annotations

import logging
import signal
import time
from contextlib import suppress
from decimal import Decimal
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

    if settings.use_grpc and (
        settings.device_registry or settings.simulation_mode != "REALTIME"
    ):
        raise ValueError(
            "Registered or offline simulation requires v2 direct MQTT; use USE_GRPC=false"
        )
    generators: dict[SensorType, SensorGenerator] = {
        SensorType.SMART_METER: SmartMeterGenerator(
            use_grpc=settings.use_grpc,
            interval_seconds=settings.interval_seconds,
            accounting_interval_seconds=settings.accounting_interval_seconds,
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
        if settings.device_registry and settings.publisher.value != "console":
            from publishers.mqtt_publisher import MqttPublisher
            from publishers.registered import RegisteredPublisher

            publisher = RegisteredPublisher(
                MqttPublisher(
                    settings.mqtt_host,
                    settings.mqtt_port,
                    client_id=settings.mqtt_client_id,
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
                if k not in ("latitude", "longitude", "timezone", "usage")
                else v
                for k, v in value.items()
            }
        )
        for key, value in json.loads(settings.home_profiles_json).items()
    }
    homes = build_default_homes()
    if settings.home_catalogue_file:
        from config.homes import load_catalogue

        homes, catalogue_profiles = load_catalogue(settings.home_catalogue_file)
        profiles = {**catalogue_profiles, **profiles}
    simulator = Simulator(
        profiles=profiles,
        homes=homes,
        generators=generators,
        publisher=publisher,
        config=SimulationConfig(
            interval_seconds=settings.interval_seconds,
            mode=settings.simulation_mode,
            speed=settings.simulation_speed,
            start=settings.simulation_start,
            fault=settings.fault_scenario,
            fault_device=settings.fault_device,
            telemetry_version="1.0" if settings.use_grpc else "2.0",
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
        if settings.max_cycles:
            for _ in range(settings.max_cycles):
                if stop_event.is_set():
                    break
                simulator.simulate_cycle()
        else:
            simulator.run(stop_event=stop_event)
    finally:
        close_channel()
        if publisher is not None:
            publisher.close()

    print("Shutting down multi-home IoT simulator...")


if __name__ == "__main__":
    print("Starting multi-home IoT simulator...")
    main()
