"""Opt-in deterministic offline fault fixtures; never active in normal operation."""

from copy import deepcopy
from datetime import datetime, timedelta


def inject(messages: list[dict], scenario: str = "none") -> list[dict]:
    scenario = {"device_outage": "outage", "export_spike": "power_spike"}.get(
        scenario, scenario
    )
    rows = deepcopy(messages)
    if scenario == "none":
        return rows
    if scenario == "mqtt_disconnection":
        return rows
    if scenario == "unauthorized_device":
        for row in rows:
            row["device_id"] = "00000000-0000-0000-0000-000000000001"
        return rows
    if scenario == "missing_interval":
        return [row for row in rows if row.get("sequence_number", 1) % 3 != 2]
    if scenario == "outage":
        return []
    if scenario == "duplicate":
        return rows + deepcopy(rows)
    if scenario == "out_of_order":
        return list(reversed(rows))
    if scenario == "packet_loss":
        return (
            [row for row in rows if row.get("sequence_number", 1) % 2 == 1]
            if all("sequence_number" in r for r in rows)
            else rows[::2]
        )
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
                if scenario == "power_spike" and field == "grid_export_energy_kwh":
                    row["data"][field] = 1000000000
                if scenario == "power_spike" and field.endswith("_power_w"):
                    row["data"][field] = 1000000000
    return rows
