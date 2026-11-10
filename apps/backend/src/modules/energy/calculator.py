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

    VERSION = "v1"

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
        """Conservatively cap eligible export by measured grid export and net generation."""
        net_surplus = max(0, generation_wh - consumption_wh)
        return max(0, min(grid_export_wh, net_surplus))

    @staticmethod
    def interval_bounds(measured_at, minutes: int = 15):
        """Return UTC-aligned interval bounds for a timestamp."""
        from datetime import timedelta

        if measured_at.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware")
        start_minute = (measured_at.minute // minutes) * minutes
        start = measured_at.replace(
            minute=start_minute, second=0, microsecond=0
        )
        return start, start + timedelta(minutes=minutes)
