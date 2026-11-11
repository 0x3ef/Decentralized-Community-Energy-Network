"""Explicit wall-time and accelerated offline simulation clocks."""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal


def next_sample_at(
    now: datetime, step_seconds: float, boundary_seconds: int = 900
) -> datetime:
    """Next UTC sample slot, including every accounting boundary.

    Never round a current reading backwards or invent missed observations.
    Including boundaries separately also supports cadences that do not divide
    the accounting interval (for example, seven seconds).
    """
    if now.tzinfo is None or step_seconds <= 0 or boundary_seconds <= 0:
        raise ValueError("Aware time and positive sampling intervals required")
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = now.astimezone(UTC) - epoch
    micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    step = int(Decimal(str(step_seconds)) * 1000000)
    boundary = boundary_seconds * 1000000
    if step < 1:
        raise ValueError("Sampling precision must be at least one microsecond")
    slot = min((micros // step + 1) * step, (micros // boundary + 1) * boundary)
    return epoch + timedelta(microseconds=slot)


class SimulationClock:
    def __init__(
        self, start: datetime | None = None, speed: float = 1, *, offline: bool = False
    ):
        if speed <= 0:
            raise ValueError("Clock speed must be positive")
        if start is not None and start.tzinfo is None:
            raise ValueError("Start must be timezone-aware")
        if not offline and (speed != 1 or start is not None):
            raise ValueError("Accelerated/historical clocks require offline mode")
        self.start = (start or datetime.now(UTC)).astimezone(UTC)
        self.speed = speed
        self.origin = time.monotonic()

    def now(self) -> datetime:
        return self.start + timedelta(
            seconds=(time.monotonic() - self.origin) * self.speed
        )


class DeterministicClock:
    """No wall clock: each cycle has an explicit reproducible UTC timestamp."""

    def __init__(self, start: datetime, step_seconds: float):
        if start.tzinfo is None or step_seconds <= 0:
            raise ValueError("Aware start and positive step required")
        self.current = start.astimezone(UTC)
        self.step = timedelta(seconds=step_seconds)

    def now(self):
        current = self.current
        self.current += self.step
        return current
