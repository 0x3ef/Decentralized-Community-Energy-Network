"""Publisher contract used by the gateway."""

from __future__ import annotations

from typing import Any, Protocol


class TelemetryPublisher(Protocol):
    """Interface for telemetry sinks (console and local MQTT)."""

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Publish a single telemetry message to ``topic``."""
        ...

    def close(self) -> None:
        """Release any underlying resources."""
        ...
