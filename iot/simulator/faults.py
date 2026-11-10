"""Opt-in deterministic offline fault fixtures; never active in normal operation."""

from copy import deepcopy
from datetime import datetime, timedelta


def inject(messages: list[dict], scenario: str = "none") -> list[dict]:
    rows = deepcopy(messages)
    if scenario == "none":
        return rows
    if scenario == "outage":
        return []
    if scenario == "duplicate":
        return rows + deepcopy(rows)
    if scenario == "out_of_order":
        return list(reversed(rows))
    if scenario == "packet_loss":
        return rows[::2]
    if scenario not in (
        "counter_reset",
        "clock_drift",
        "invalid_payload",
        "power_spike",
        "delay",
    ):
        raise ValueError("Unknown fault scenario")
    for row in rows:
        if scenario in ("clock_drift", "delay"):
            row["measured_at"] = (
                datetime.fromisoformat(row["measured_at"])
                + timedelta(seconds=3600 if scenario == "clock_drift" else -3600)
            ).isoformat()
        elif scenario == "invalid_payload":
            row["schema_version"] = "unsupported"
        else:
            for field in row["data"]:
                if scenario == "counter_reset" and field.endswith("_kwh"):
                    row["data"][field] = 0
                if scenario == "power_spike" and field.endswith("_power_w"):
                    row["data"][field] = 1000000000
    return rows
