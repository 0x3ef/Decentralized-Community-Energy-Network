"""Explicit wall-time and accelerated offline simulation clocks."""

from datetime import datetime, UTC, timedelta
import time


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
