"""Map friendly demo codes to provisioned UUIDs; authorization is still backend-owned."""

import json
import os
from pathlib import Path
from uuid import UUID


class RegisteredPublisher:
    def __init__(self, publisher, registry_path: str):
        self.publisher = publisher
        self.registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        for entry in self.registry.values():
            UUID(entry["device_id"])
            UUID(entry["home_id"])
            if len(os.environ.get(entry["credential_env"], "")) < 32:
                raise ValueError(
                    "Missing registered device credential environment binding"
                )

    def publish(self, topic: str, message: dict) -> None:
        entry = self.registry[message["device_id"]]
        payload = {
            **message,
            "device_id": entry["device_id"],
            "home_id": entry["home_id"],
            "credential": os.environ[entry["credential_env"]],
        }
        if message.get("schema_version") == "2.0":
            if not entry.get("community_id") or not entry.get("node_id"):
                raise ValueError("v2 registry requires approved community and node IDs")
            payload.update(community_id=entry["community_id"], node_id=entry["node_id"])
            topic = f"solar/{entry['community_id']}/{entry['node_id']}/{entry['device_id']}/telemetry"
        else:
            topic = f"solar/{entry['home_id']}/{entry['device_id']}/telemetry"
        self.publisher.publish(topic, payload)

    def close(self):
        self.publisher.close()
