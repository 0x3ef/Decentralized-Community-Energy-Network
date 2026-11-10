"""Map friendly demo codes to provisioned UUIDs; authorization is still backend-owned."""

import json
import os
from uuid import UUID


class RegisteredPublisher:
    def __init__(self, publisher, registry_path: str):
        self.publisher = publisher
        self.registry = json.loads(open(registry_path, encoding="utf-8").read())
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
        self.publisher.publish(
            f"solar/{entry['home_id']}/{entry['device_id']}/telemetry", payload
        )

    def close(self):
        self.publisher.close()
