"""Transport rejection and registration checks do not claim a sent hash is delivery."""

from datetime import datetime, UTC
import json
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
    monkeypatch.setattr(
        "publishers.mqtt_publisher.mqtt.Client", lambda **kwargs: client
    )
    publisher = MqttPublisher("unused")
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
