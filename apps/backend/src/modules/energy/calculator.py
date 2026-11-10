"""Pure energy calculations using integer watt-hours."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnergyDeltas:
    """Incremental energy values measured during one telemetry sample."""

    generation_wh: int = 0
    consumption_wh: int = 0
    grid_import_wh: int = 0
    grid_export_wh: int = 0
    battery_charge_wh: int = 0
    battery_discharge_wh: int = 0


class EnergyCalculator:
    """Calculate energy deltas and export eligibility without database access."""

    VERSION = "v2-authoritative-export"

    @staticmethod
    def counter_delta(previous_wh: int | None, current_wh: int | None) -> int:
        """Return a non-negative counter delta.

        A lower current value is treated as a device counter reset. The reset
        sample establishes a new baseline and does not create negative energy.
        """
        if current_wh is None or current_wh < 0:
            return 0
        if previous_wh is None or current_wh < previous_wh:
            return 0
        return current_wh - previous_wh

    @staticmethod
    def eligible_export(
        generation_wh: int,
        consumption_wh: int,
        grid_export_wh: int,
    ) -> int:
        """Authoritative export metering determines injection, not generation."""
        return max(0, grid_export_wh)

    @staticmethod
    def interval_bounds(measured_at, minutes: int = 15):
        """Return UTC-aligned interval bounds for a timestamp."""
        from datetime import datetime, timedelta, timezone

        if measured_at.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware")
        seconds = int(minutes * 60)
        if seconds <= 0:
            raise ValueError("Settlement interval must be positive")
        start = datetime.fromtimestamp(
            int(measured_at.timestamp()) // seconds * seconds, tz=timezone.utc
        )
        return start, start + timedelta(seconds=seconds)
