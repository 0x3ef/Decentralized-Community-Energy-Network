"""Process-wide gRPC channel and stub factories.

A single channel is reused by every generator so that adding homes does
not open additional TCP connections. Stubs are cached and protected by
a **reentrant** lock because ``_get_stub`` calls ``get_channel`` while
already holding the lock, and ``threading.Lock`` is not reentrant.

The channel is opened lazily with a bounded ``connect`` timeout and the
``ready`` wait is capped, so a misbehaving gateway cannot block the
simulator forever.
"""

from __future__ import annotations

import logging
import os
from threading import RLock
from typing import TypeVar

import grpc
from grpc import Channel

from grpc_client import sensor_pb2_grpc

logger = logging.getLogger(__name__)

_GATEWAY_ADDRESS = os.getenv("GATEWAY_ADDRESS", "gateway:50051")
_CONNECT_TIMEOUT_SECONDS = float(os.getenv("GRPC_CONNECT_TIMEOUT", "5.0"))

StubT = TypeVar("StubT")

_channel: Channel | None = None
_stubs: dict[str, object] = {}
_lock = RLock()


def get_channel() -> Channel:
    """Return the process-wide gRPC channel, creating it on first call.

    Raises:
        ConnectionError: If the gateway does not become ready within
            ``_CONNECT_TIMEOUT_SECONDS``.
    """
    global _channel
    with _lock:
        if _channel is None:
            logger.info("Opening gRPC channel to %s", _GATEWAY_ADDRESS)
            _channel = grpc.insecure_channel(_GATEWAY_ADDRESS)
            try:
                grpc.channel_ready_future(_channel).result(
                    timeout=_CONNECT_TIMEOUT_SECONDS
                )
            except grpc.FutureTimeoutError as exc:
                _channel.close()
                _channel = None
                raise ConnectionError(
                    f"gRPC gateway {_GATEWAY_ADDRESS} not ready after "
                    f"{_CONNECT_TIMEOUT_SECONDS}s"
                ) from exc
        return _channel


def _get_stub(name: str, stub_cls: type[StubT]) -> StubT:  # noqa: UP047
    """Return a cached stub instance for ``stub_cls``.

    Uses the reentrant lock so that the inner ``get_channel`` call can
    acquire the same lock without deadlocking.
    """
    with _lock:
        cached = _stubs.get(name)
        if cached is None:
            cached = stub_cls(get_channel())
            _stubs[name] = cached
        return cached


def get_smart_meter_stub() -> sensor_pb2_grpc.SmartMeterSensorServiceStub:
    """Return the smart meter stub."""
    return _get_stub(
        "smart_meter", sensor_pb2_grpc.SmartMeterSensorServiceStub
    )


def get_solar_inverter_stub() -> (
    sensor_pb2_grpc.SolarInverterSensorServiceStub
):
    """Return the solar inverter stub."""
    return _get_stub(
        "solar_inverter",
        sensor_pb2_grpc.SolarInverterSensorServiceStub,
    )


def get_weather_stub() -> sensor_pb2_grpc.WeatherSensorServiceStub:
    """Return the weather sensor stub."""
    return _get_stub(
        "weather", sensor_pb2_grpc.WeatherSensorServiceStub
    )


def get_battery_stub() -> sensor_pb2_grpc.BatteryMonitorSensorServiceStub:
    """Return the battery monitor stub."""
    return _get_stub(
        "battery", sensor_pb2_grpc.BatteryMonitorSensorServiceStub
    )


def close_channel() -> None:
    """Close the shared channel. Intended for graceful shutdown."""
    global _channel
    with _lock:
        if _channel is not None:
            _channel.close()
            _channel = None
            _stubs.clear()
