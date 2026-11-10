"""Transport lifecycle, caching, bounded failure and broker delivery checks."""

from concurrent import futures
from datetime import datetime, UTC
import json
import queue
import grpc
import pytest
import paho.mqtt.client as mqtt
from grpc_client import channel
from publishers.mqtt_publisher import MqttPublisher


@pytest.mark.integration
def test_shared_channel_and_stub_cache_shutdown(monkeypatch):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    channel.close_channel()
    monkeypatch.setattr(channel, "_GATEWAY_ADDRESS", f"127.0.0.1:{port}")
    try:
        first = channel.get_channel()
        assert channel.get_channel() is first
        for factory in (
            channel.get_smart_meter_stub,
            channel.get_solar_inverter_stub,
            channel.get_weather_stub,
            channel.get_battery_stub,
        ):
            assert factory() is factory()
        channel.close_channel()
        assert channel._channel is None and not channel._stubs
    finally:
        channel.close_channel()
        server.stop(0).wait()


def test_gateway_connection_timeout_resets_channel(monkeypatch):
    channel.close_channel()
    monkeypatch.setattr(channel, "_GATEWAY_ADDRESS", "127.0.0.1:1")
    monkeypatch.setattr(channel, "_CONNECT_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(ConnectionError, match="not ready"):
        channel.get_channel()
    assert channel._channel is None


@pytest.mark.integration
def test_mqtt_publisher_validated_delivery_and_close(mqtt_host):
    inbox = queue.Queue()
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    subscriber.on_message = lambda client, userdata, message: inbox.put(
        json.loads(message.payload)
    )
    import threading

    ready = threading.Event()
    subscriber.on_subscribe = lambda *args: ready.set()
    subscriber.connect(mqtt_host, 1883)
    subscriber.subscribe("solar/TEST-TRANSPORT/#", qos=1)
    subscriber.loop_start()
    assert ready.wait(5)
    publisher = MqttPublisher(mqtt_host, client_id="transport-lifecycle")
    try:
        payload = {
            "schema_version": "1.0",
            "device_id": "SM-1",
            "home_id": "TEST-TRANSPORT",
            "sensor_type": "smart_meter",
            "sequence_number": 42,
            "measured_at": datetime.now(UTC).isoformat(),
            "data": {"voltage_v": 120},
        }
        publisher.publish("solar/TEST-TRANSPORT/SM-1/telemetry", payload)
        received = inbox.get(timeout=5)
        assert (
            received["sequence_number"] == 42 and received["data"]["voltage_v"] == 120
        )
    finally:
        publisher.close()
        subscriber.disconnect()
        subscriber.loop_stop()
