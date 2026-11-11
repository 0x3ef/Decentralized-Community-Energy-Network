"""End-to-end integration tests — require a live broker.

These tests run inside the docker-compose network via
``make test-integration``. They are skipped automatically when the
broker or the gateway cannot be reached.
"""

from __future__ import annotations

import json
import queue
import time
from datetime import UTC, datetime

import grpc
import paho.mqtt.client as mqtt
import pytest

from grpc_client import sensor_pb2, sensor_pb2_grpc

pytestmark = pytest.mark.integration


def _wait_for_message(
    client: mqtt.Client,
    inbox: queue.Queue[tuple[str, dict]],
    topic_prefix: str,
    timeout: float = 5.0,
) -> tuple[str, dict]:
    """Block until a message arrives on ``topic_prefix`` or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            topic, payload = inbox.get(timeout=0.2)
        except queue.Empty:
            continue
        if topic.startswith(topic_prefix):
            return topic, payload
    raise AssertionError(f"No message on {topic_prefix} within {timeout}s")


def test_gateway_republishes_to_mqtt(mqtt_host: str, mqtt_port: int, gateway_address: str) -> None:
    """Send a smart-meter reading through gRPC and expect it on MQTT."""
    inbox: queue.Queue[tuple[str, dict]] = queue.Queue()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="test-subscriber",
    )

    def _on_message(_c, _u, msg) -> None:
        inbox.put((msg.topic, json.loads(msg.payload)))

    client.on_message = _on_message
    client.connect(mqtt_host, mqtt_port, keepalive=30)
    client.subscribe("solar/#", qos=1)
    client.loop_start()

    try:
        channel = grpc.insecure_channel(gateway_address)
        stub = sensor_pb2_grpc.SmartMeterSensorServiceStub(channel)
        stub.SendSmartMeterRequest(
            sensor_pb2.SmartMeterSensorRequest(
                device_id="SM-INT-001",
                home_id="HOME-INT",
                timestamp=datetime.now(UTC).isoformat(),
                sequence=1,
                measurements=sensor_pb2.SmartMeterMeasurements(
                    voltage_v=120.0
                ),
            )
        )
        channel.close()

        _topic, payload = _wait_for_message(
            client, inbox, "solar/HOME-INT/SM-INT-001/"
        )
        assert payload["device_id"] == "SM-INT-001"
        assert payload["sensor_type"] == "smart_meter"
        assert payload["data"]["voltage_v"] == 120.0
    finally:
        client.loop_stop()
        client.disconnect()
