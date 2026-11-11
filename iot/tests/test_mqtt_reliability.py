"""Transport rejection and registration checks do not claim a sent hash is delivery."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from publishers.mqtt_publisher import MqttPublisher
from publishers.registered import RegisteredPublisher


@pytest.fixture
def message():
    return {
        "schema_version": "1.0",
        "device_id": "meter",
        "home_id": "home",
        "sensor_type": "smart_meter",
        "sequence_number": 7,
        "measured_at": datetime.now(UTC).isoformat(),
        "data": {"voltage_v": 120},
    }


def test_publish_error_is_reported_for_retry(monkeypatch, message):
    client = Mock()
    client.publish.return_value.rc = 4
    client.loop_start.side_effect = lambda: client.on_connect(client, None, None, 0)
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    publisher = MqttPublisher("unused")
    with pytest.raises(ConnectionError):
        publisher.publish("solar/home/meter/telemetry", message)
    with pytest.raises(ValueError):
        publisher.publish("solar/another/device/telemetry", message)


def test_missing_ack_is_an_unknown_outcome(monkeypatch, message):
    client = Mock()
    client.publish.return_value.rc = 0
    client.publish.return_value.is_published.return_value = False
    client.loop_start.side_effect = lambda: client.on_connect(client, None, None, 0)
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    publisher = MqttPublisher("unused")
    client.publish.return_value.wait_for_publish.reset_mock()
    with pytest.raises(TimeoutError):
        publisher.publish("solar/home/meter/telemetry", message)
    client.publish.return_value.wait_for_publish.assert_called_once()


def test_registry_maps_friendly_names_without_exposing_credentials(
    tmp_path, monkeypatch, message
):
    file = tmp_path / "registry.json"
    file.write_text(
        json.dumps(
            {
                "meter": {
                    "device_id": "22222222-2222-4222-8222-222222222222",
                    "home_id": "11111111-1111-4111-8111-111111111111",
                    "credential_env": "TEST_METER_CREDENTIAL",
                }
            }
        )
    )
    monkeypatch.setenv(
        "TEST_METER_CREDENTIAL", "test-meter-credential-at-least-32-characters"
    )
    transport = Mock()
    RegisteredPublisher(transport, str(file)).publish("ignored", message)
    topic, payload = transport.publish.call_args.args
    assert topic.endswith("/22222222-2222-4222-8222-222222222222/telemetry")
    assert payload["credential"] and "credential" not in message
    monkeypatch.delenv("TEST_METER_CREDENTIAL")
    with pytest.raises(ValueError):
        RegisteredPublisher(transport, str(file))


def test_delivery_without_qos_is_rejected():
    with pytest.raises(ValueError):
        MqttPublisher("unused", qos=0)


def test_constructor_waits_for_broker_acknowledgement(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    client = Mock()
    started = Event()
    client.loop_start.side_effect = started.set
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(MqttPublisher, "unused", publish_timeout=1)
        assert started.wait(1)
        assert not pending.done()
        client.publish.assert_not_called()
        client.on_connect(client, None, None, 0)
        publisher = pending.result(timeout=1)
        assert publisher._connected.is_set()


def test_connection_timeout_stops_network_thread(monkeypatch):
    client = Mock()
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    with pytest.raises(ConnectionError, match="session was not established"):
        MqttPublisher("unused", publish_timeout=0.01)
    client.disconnect.assert_called_once()
    client.loop_stop.assert_called_once()
    client.publish.assert_not_called()


def test_publish_waits_for_reconnection_without_losing_sample(monkeypatch, message):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    client = Mock()
    client.loop_start.side_effect = lambda: client.on_connect(client, None, None, 0)
    client.publish.return_value.rc = 0
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    publisher = MqttPublisher("unused", publish_timeout=1)
    client.on_disconnect(client, None, None, 1)
    client.publish.reset_mock()
    waiting = Event()
    original_wait = publisher._connected.wait

    def wait(timeout):
        waiting.set()
        return original_wait(timeout)

    monkeypatch.setattr(publisher._connected, "wait", wait)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(publisher.publish, "solar/home/meter/telemetry", message)
        assert waiting.wait(1)
        client.publish.assert_not_called()
        client.on_connect(client, None, None, 0)
        pending.result(timeout=1)
    delivered = [
        call
        for call in client.publish.call_args_list
        if call.args[0].endswith("/telemetry")
    ]
    assert len(delivered) == 1
    assert (
        json.loads(delivered[0].args[1])["sequence_number"]
        == message["sequence_number"]
    )


def test_disconnected_timeout_never_publishes(monkeypatch, message):
    client = Mock()
    client.loop_start.side_effect = lambda: client.on_connect(client, None, None, 0)
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    publisher = MqttPublisher("unused", publish_timeout=0.01)
    client.on_disconnect(client, None, None, 1)
    client.publish.reset_mock()
    with pytest.raises(ConnectionError, match="remains disconnected"):
        publisher.publish("solar/home/meter/telemetry", message)
    client.publish.assert_not_called()
