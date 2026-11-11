"""Shared pytest fixtures."""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime

import pytest

from config.homes import build_home
from models.home import Home


@pytest.fixture()
def fixed_time() -> datetime:
    """A deterministic UTC timestamp."""
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def sample_home() -> Home:
    """A home with all four sensors."""
    return build_home(
        "HOME-TEST-001", "Testville", solar_kw=5.0, battery_kwh=10.0
    )


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def mqtt_host() -> str:
    """Return the MQTT host or skip if unreachable."""
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    if not _port_open(host, port):
        pytest.skip(f"MQTT broker not reachable at {host}:{port}")
    return host


@pytest.fixture(scope="session")
def gateway_address() -> str:
    """Return the gateway address or skip if unreachable."""
    addr = os.getenv("GATEWAY_ADDRESS", "localhost:50051")
    host, port = addr.split(":")
    if not _port_open(host, int(port)):
        pytest.skip(f"Gateway not reachable at {addr}")
    return addr

@pytest.fixture(scope="session")
def mqtt_port() -> int:
    return int(os.getenv("MQTT_PORT", "1883"))
