"""Small helper for stateful random-walk simulation.

Using a random walk instead of independent ``random.uniform`` calls
produces realistic, autocorrelated time series (values change slowly
instead of jumping every cycle).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random


@dataclass(slots=True)
class BoundedWalk:
    """Random walk bounded to ``[lo, hi]`` with reflective boundaries.

    Args:
        lo: Lower bound of the walk.
        hi: Upper bound of the walk.
        step: Maximum absolute change per :meth:`next` call.
        initial: Initial value; defaults to the midpoint.
    """

    lo: float
    hi: float
    step: float
    initial: float | None = None
    rng: Random = field(default_factory=Random, repr=False)
    _value: float = field(init=False)

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise ValueError("lo must be <= hi")
        if self.step <= 0:
            raise ValueError("step must be positive")
        mid = (self.lo + self.hi) / 2
        self._value = self.initial if self.initial is not None else mid
        self._value = max(self.lo, min(self.hi, self._value))

    @property
    def value(self) -> float:
        """Current value of the walk."""
        return self._value

    def next(self) -> float:
        """Advance the walk and return the new value."""
        delta = self.rng.uniform(-self.step, self.step)
        candidate = self._value + delta
        # Reflect at the boundaries to avoid sticking to an edge.
        if candidate < self.lo:
            candidate = self.lo + (self.lo - candidate)
        elif candidate > self.hi:
            candidate = self.hi - (candidate - self.hi)
        self._value = max(self.lo, min(self.hi, candidate))
        return self._value
