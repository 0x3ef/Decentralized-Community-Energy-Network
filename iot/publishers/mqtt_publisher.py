"""MQTT publisher for the local Mosquitto broker."""

from __future__ import annotations

import json
import logging
import ssl
import time
from threading import Lock
from typing import Any

import paho.mqtt.client as mqtt

from schemas.telemetry import TelemetryPayload

logger = logging.getLogger(__name__)


class MqttPublisher:
    """Publish telemetry to any MQTT 3.1.1/5 broker.

    Args:
        host: Broker hostname.
        port: Broker port.
        client_id: Unique MQTT client identifier.
        qos: Delivery guarantee (0, 1 or 2). Defaults to 1.
        tls: Enable mutual TLS.
        ca_cert: Path to the CA certificate (TLS only).
        client_cert: Path to the client certificate (TLS only).
        client_key: Path to the client private key (TLS only).
    """

    def __init__(
        self,
        host: str,
        port: int = 1883,
        client_id: str = "solar-gateway",
        qos: int = 1,
        tls: bool = False,
        ca_cert: str | None = None,
        client_cert: str | None = None,
        client_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        publish_timeout: float = 10,
    ) -> None:
        if qos not in (1, 2):
            raise ValueError("Durable telemetry requires QoS 1 or 2")
        self._timeout = publish_timeout
        self._status_topic = f"solar/status/{client_id}"
        self._qos = qos
        self._lock = Lock()

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )

        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.max_queued_messages_set(1000)
        if username:
            self._client.username_pw_set(username, password)

        if tls:
            if not ca_cert or bool(client_cert) != bool(client_key):
                raise ValueError(
                    "TLS requires a CA certificate and a complete optional client certificate/key pair"
                )
            self._client.tls_set(
                ca_certs=ca_cert,
                certfile=client_cert,
                keyfile=client_key,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

        self._client.will_set(
            self._status_topic,
            json.dumps({"state": "OFFLINE", "client_id": client_id}),
            qos=1,
            retain=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        deadline = time.monotonic() + publish_timeout
        delay = 0.25
        while True:
            try:
                self._client.connect(host, port, keepalive=60)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(delay, max(0, deadline - time.monotonic())))
                delay = min(5, delay * 2)
        self._client.loop_start()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any = None,
    ) -> None:
        if rc == 0:
            client.publish(
                self._status_topic, json.dumps({"state": "ONLINE"}), qos=1, retain=True
            )
            logger.info("Connected to MQTT broker")
        else:
            logger.error("MQTT connection failed (rc=%s)", rc)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any = None,
    ) -> None:
        logger.warning("MQTT disconnected (rc=%s)", rc)

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Validate ``message`` and publish it as JSON to ``topic``."""
        expected = (
            f"solar/{message['community_id']}/{message['node_id']}/{message['device_id']}/telemetry"
            if message.get("schema_version") == "2.0"
            else f"solar/{message['home_id']}/{message['device_id']}/telemetry"
        )
        if topic != expected:
            raise ValueError("Telemetry topic does not match device identity")
        payload_model = TelemetryPayload.model_validate(
            {k: v for k, v in message.items() if k != "credential"}
        )
        envelope = payload_model.to_mqtt_payload()
        if "credential" in message:
            envelope["credential"] = message["credential"]
        payload = json.dumps(envelope, default=str)
        if len(payload.encode()) > 65536:
            raise ValueError("Telemetry payload exceeds 64 KiB")

        with self._lock:
            info = self._client.publish(topic, payload, qos=self._qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish was not accepted (rc={info.rc})")
        info.wait_for_publish(timeout=self._timeout)
        if not info.is_published():
            raise TimeoutError(
                "MQTT acknowledgement timed out; preserve sequence and retry"
            )

    def close(self) -> None:
        """Stop the network loop and disconnect."""
        info = self._client.publish(
            self._status_topic, json.dumps({"state": "OFFLINE"}), qos=1, retain=True
        )
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            info.wait_for_publish(timeout=min(self._timeout, 2))
        self._client.disconnect()
        self._client.loop_stop()
