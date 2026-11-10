"""gRPC gateway entry point: receive telemetry and republish to MQTT."""

from __future__ import annotations

import logging
import signal
from concurrent import futures
from contextlib import suppress
from threading import Event

import grpc

from config.settings import PublisherKind, Settings
from gateway.servicers import (
    BatteryMonitorServicer,
    SmartMeterServicer,
    SolarInverterServicer,
    WeatherServicer,
)
from grpc_client import sensor_pb2_grpc
from publishers.base import TelemetryPublisher
from publishers.console_publisher import ConsolePublisher
from publishers.mqtt_publisher import MqttPublisher

logger = logging.getLogger("gateway")


def _build_publisher(settings: Settings) -> TelemetryPublisher:
    """Build the publisher requested by ``settings``."""
    if settings.publisher == PublisherKind.MQTT:
        return MqttPublisher(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            client_id=settings.mqtt_client_id,
            qos=settings.mqtt_qos,
            username=settings.mqtt_username, password=settings.mqtt_password,
            tls=settings.mqtt_tls, ca_cert=settings.mqtt_ca_cert,
            client_cert=settings.mqtt_client_cert, client_key=settings.mqtt_client_key,
        )
    return ConsolePublisher()


def _install_signal_handlers(stop_event: Event) -> None:
    def _handler(signum: int, _frame: object) -> None:
        logger.info("Received signal %d, shutting down", signum)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            signal.signal(sig, _handler)


def main() -> None:
    """Start the gRPC server and block until signaled."""
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    publisher = _build_publisher(settings)

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers),
        options=[("grpc.max_receive_message_length", 4 * 1024 * 1024)],
    )

    sensor_pb2_grpc.add_SmartMeterSensorServiceServicer_to_server(
        SmartMeterServicer(publisher), server
    )
    sensor_pb2_grpc.add_SolarInverterSensorServiceServicer_to_server(
        SolarInverterServicer(publisher), server
    )
    sensor_pb2_grpc.add_WeatherSensorServiceServicer_to_server(
        WeatherServicer(publisher), server
    )
    sensor_pb2_grpc.add_BatteryMonitorSensorServiceServicer_to_server(
        BatteryMonitorServicer(publisher), server
    )

    address = f"0.0.0.0:{settings.grpc_port}"
    server.add_insecure_port(address)
    server.start()
    logger.info("Gateway listening on %s", address)

    stop_event = Event()
    _install_signal_handlers(stop_event)

    try:
        stop_event.wait()
    finally:
        server.stop(grace=5).wait()
        publisher.close()
        logger.info("Gateway stopped")


if __name__ == "__main__":
    main()
