"""Restart only the disposable test broker and verify actual client recovery."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt
from src.core.config import Config

from publishers.mqtt_publisher import MqttPublisher


def test_publisher_recovers_after_disposable_broker_restart():
    root = Path(__file__).resolve().parents[3]
    # This integration case must never stop the shared development broker.
    assert Config.MQTT_PORT == 18884, (
        "Use scripts/test_backend.sh and its isolated test broker"
    )
    inbox = Queue()
    subscribed, connected, disconnected = Event(), Event(), Event()
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    subscriber.reconnect_delay_set(min_delay=1, max_delay=2)
    subscriber.on_connect = lambda client, *args: client.subscribe(
        "solar/reconnect-home/#", qos=1
    )
    subscriber.on_subscribe = lambda *args: subscribed.set()
    subscriber.on_message = lambda client, userdata, message: inbox.put(
        json.loads(message.payload)
    )
    publisher = None
    subscriber.connect(Config.MQTT_HOST, Config.MQTT_PORT)
    subscriber.loop_start()

    def payload(sequence):
        return dict(
            schema_version="1.0",
            home_id="reconnect-home",
            device_id="reconnect-meter",
            sensor_type="smart_meter",
            sequence_number=sequence,
            measured_at=datetime.now(UTC).isoformat(),
            data={"voltage_v": 120},
        )

    topic = "solar/reconnect-home/reconnect-meter/telemetry"
    try:
        publisher = MqttPublisher(
            Config.MQTT_HOST,
            Config.MQTT_PORT,
            client_id="restart-test-" + uuid4().hex,
        )
        # Observe the callbacks without replacing their lifecycle behavior.
        # In particular, reconnect must restore the publisher's readiness event.
        original_connect = publisher._client.on_connect
        original_disconnect = publisher._client.on_disconnect

        def on_connect(client, userdata, flags, reason_code, properties):
            original_connect(client, userdata, flags, reason_code, properties)
            if reason_code == 0:
                connected.set()

        def on_disconnect(client, userdata, flags, reason_code, properties):
            original_disconnect(client, userdata, flags, reason_code, properties)
            disconnected.set()

        publisher._client.on_connect = on_connect
        publisher._client.on_disconnect = on_disconnect
        assert subscribed.wait(10)
        publisher.publish(topic, payload(1))
        assert inbox.get(timeout=10)["sequence_number"] == 1
        subscribed.clear()
        subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                "solar-prototype-tests",
                "-f",
                str(root / "infrastructure/docker/compose.tests.yml"),
                "restart",
                "mqtt",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        assert disconnected.wait(10), "Publisher did not observe the broker outage"
        assert connected.wait(15), "Publisher did not acknowledge reconnection"
        assert subscribed.wait(15), "Subscriber did not restore its subscription"
        publisher.publish(topic, payload(2))
        assert inbox.get(timeout=10)["sequence_number"] == 2
    finally:
        try:
            if publisher is not None:
                publisher.close()
        finally:
            subscriber.disconnect()
            subscriber.loop_stop()
