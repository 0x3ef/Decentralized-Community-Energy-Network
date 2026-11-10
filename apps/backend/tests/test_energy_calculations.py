from datetime import datetime, timezone, timedelta
from src.modules.energy.calculator import EnergyCalculator


def test_authoritative_export_not_generation_or_inferred_surplus():
    assert EnergyCalculator.eligible_export(10000, 6000, 4000) == 4000
    assert EnergyCalculator.eligible_export(10000, 6000, 5000) == 5000
    assert EnergyCalculator.eligible_export(10000, 0, 0) == 0


def test_cumulative_counters_reset_and_baseline():
    assert EnergyCalculator.counter_delta(1000, 1500) == 500
    assert EnergyCalculator.counter_delta(1000, 200) == 0
    assert EnergyCalculator.counter_delta(None, 1000) == 0


def test_interval_alignment_is_utc():
    start, end = EnergyCalculator.interval_bounds(
        datetime(2026, 1, 1, 10, 7, tzinfo=timezone(timedelta(hours=-5)))
    )
    assert start.hour == 15 and start.minute == 0 and end.minute == 15
