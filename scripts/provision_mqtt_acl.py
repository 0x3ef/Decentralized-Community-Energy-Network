#!/usr/bin/env python3
"""Render exact community/node/device broker grants from a public registry.

Passwords and TLS private keys are managed separately. No wildcard write grant
or embedded device credential is produced by this command.
"""

import argparse
import json
from pathlib import Path
from uuid import UUID


def render(registry, gateway_user=None):
    lines = [
        "user solar-subscriber",
        "topic read solar/+/+/+/telemetry",
        "topic read solar/+/+/telemetry",
        "topic read solar/status/+",
        "",
    ]
    topics = []
    for entry in registry.values():
        community, node, device = (
            str(UUID(entry[k])) for k in ("community_id", "node_id", "device_id")
        )
        username = f"meter-{device}"
        topic = f"solar/{community}/{node}/{device}/telemetry"
        topics.append(topic)
        lines.extend(
            [
                f"user {username}",
                f"topic write {topic}",
                f"topic write solar/status/{username}",
                "",
            ]
        )
    if gateway_user:
        if (
            not gateway_user.replace("-", "").replace("_", "").isalnum()
            or gateway_user == "solar-subscriber"
        ):
            raise ValueError(
                "Gateway principal must be distinct and contain letters/digits/_/-"
            )
        lines.append(f"user {gateway_user}")
        lines.extend(f"topic write {topic}" for topic in sorted(set(topics)))
        lines.append(f"topic write solar/status/{gateway_user}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gateway-user")
    args = parser.parse_args()
    text = render(json.loads(args.registry.read_text()), args.gateway_user)
    with args.output.open("x") as file:
        file.write(text)
