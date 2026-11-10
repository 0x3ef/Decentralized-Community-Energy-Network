"""MQTT publisher for the local Mosquitto broker."""

from __future__ import annotations

import json
import logging
import ssl
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
    ) -> None:
        self._qos = qos
        self._lock = Lock()

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )

        if tls:
            if not (ca_cert and client_cert and client_key):
                raise ValueError(
                    "TLS requires ca_cert, client_cert and client_key"
                )
            self._client.tls_set(
                ca_certs=ca_cert,
                certfile=client_cert,
                keyfile=client_key,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()

    def _on_connect(
        self, client: mqtt.Client, userdata: Any, flags: Any, rc: int,
        properties: Any = None,
    ) -> None:
        if rc == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error("MQTT connection failed (rc=%s)", rc)

    def _on_disconnect(
        self, client: mqtt.Client, userdata: Any, flags: Any, rc: int,
        properties: Any = None,
    ) -> None:
        logger.warning("MQTT disconnected (rc=%s)", rc)

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Validate ``message`` and publish it as JSON to ``topic``."""
        payload_model = TelemetryPayload.model_validate(message)
        payload = json.dumps(payload_model.to_mqtt_payload(), default=str)

        with self._lock:
            info = self._client.publish(topic, payload, qos=self._qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Publish failed to %s (rc=%s)", topic, info.rc)

    def close(self) -> None:
        """Stop the network loop and disconnect."""
        self._client.loop_stop()
        self._client.disconnect()
