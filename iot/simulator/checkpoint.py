"""Atomic local simulator checkpoint. It contains no device credentials."""

import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def save(path: str, sequences: dict, models: dict, pending: dict | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "pending": pending or {},
        "sequences": sequences,
        "homes": {
            key: {
                "counters": model.counters,
                "stored": model.stored,
                "previous": model.previous.isoformat() if model.previous else None,
                "day": str(model.day) if model.day else None,
                "daily_generation": model.daily_generation,
                "rng": model.rng.getstate(),
                "state": model.state,
            }
            for key, model in models.items()
        },
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(snapshot, stream, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(target)


def load(path: str, sequences: dict, models: dict, pending: dict | None = None) -> None:
    target = Path(path)
    if not target.exists():
        return
    data = json.loads(target.read_text())

    def tuples(value):
        return tuple(tuples(v) for v in value) if isinstance(value, list) else value

    if set(data["homes"]) != set(models):
        raise ValueError("Checkpoint home identities differ from configured registry")
    for key, model in models.items():
        row = data["homes"][key]
        model.counters = {k: Decimal(v) for k, v in row["counters"].items()}
        model.stored = Decimal(row["stored"])
        model.previous = (
            datetime.fromisoformat(row["previous"]) if row["previous"] else None
        )
        model.day = datetime.fromisoformat(row["day"]).date() if row["day"] else None
        model.daily_generation = Decimal(row["daily_generation"])
        model.rng.setstate(tuples(row["rng"]))
        model.state = {k: Decimal(v) for k, v in row["state"].items()}
    if pending is not None:
        pending.update(data.get("pending", {}))
    sequences.update({key: int(value) for key, value in data["sequences"].items()})
