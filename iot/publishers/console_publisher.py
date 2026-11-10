"""Console publisher for local development."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConsolePublisher:
    """Log telemetry messages through the standard logger."""

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Log one message prefixed with its MQTT topic."""
        logger.info("[%s] %s", topic, json.dumps(message, default=str))

    def close(self) -> None:
        """No-op: nothing to release."""
        return None
