"""Conservation and clock tests exercise the shared physical model."""

from datetime import datetime, UTC, timedelta
from decimal import Decimal
import pytest
from config.homes import build_home
from simulator.physics import HomeEnergyModel, HomeProfile
from simulator.clock import SimulationClock


@pytest.mark.parametrize("solar,battery", [(0, 0), (5, 0), (5, 10), (0, 10)])
def test_full_day_conservation_soc_and_counters(solar, battery):
    model = HomeEnergyModel(
        build_home("HOME-CALI-001", "Cali", solar, battery), seed=42
    )
    start = datetime(2026, 6, 21, tzinfo=UTC)
    last = {k: Decimal(0) for k in model.counters}
    for minute in range(0, 1440, 5):
        s = model.step(start + timedelta(minutes=minute))
        assert abs(
            s["generation"]
            + s["import"]
            + s["discharge"]
            - s["consumption"]
            - s["export"]
            - s["charge"]
        ) < Decimal(".00000001")
        assert not (s["charge"] and s["discharge"])
        if battery:
            assert Decimal("9.999") <= s["soc"] <= Decimal("95.001")
        for key, value in model.counters.items():
            assert value >= last[key]
        last = dict(model.counters)
        if solar == 0:
            assert s["export"] == 0


def test_night_solar_is_zero_and_noon_exceeds_dawn():
    m = HomeEnergyModel(build_home("HOME-CALI-001", "Cali", 5, 0), seed=1)
    at = datetime(2026, 6, 21, tzinfo=UTC)
    assert m.solar_factor(at + timedelta(hours=5)) == 0
    assert m.solar_factor(at + timedelta(hours=17)) > m.solar_factor(
        at + timedelta(hours=12)
    )


def test_three_homes_have_independent_energy_and_seeded_state():
    models = [
        HomeEnergyModel(build_home(f"HOME-CALI-00{i}", "Cali", i * 2, 0), seed=i)
        for i in range(1, 4)
    ]
    at = datetime(2026, 6, 21, 17, tzinfo=UTC)
    for m in models:
        m.step(at)
        m.step(at + timedelta(seconds=37))
    assert len({m.counters["generation"] for m in models}) == 3
    before = dict(models[1].counters)
    models[0].step(at + timedelta(seconds=80))
    assert models[1].counters == before


def test_repeat_timestamp_does_not_integrate_and_time_regression_rejected():
    m = HomeEnergyModel(build_home("HOME-CALI-001", "Cali", 5, 0), seed=1)
    at = datetime.now(UTC)
    m.step(at)
    m.step(at)
    assert m.counters["generation"] == 0
    with pytest.raises(ValueError):
        m.step(at - timedelta(seconds=1))


@pytest.mark.parametrize(
    "kwargs", [{"speed": 2}, {"start": datetime.now(UTC)}, {"speed": 0}]
)
def test_live_clock_rejects_accelerated_or_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        SimulationClock(**kwargs)


def test_offline_clock_speed_and_utc(monkeypatch):
    monkeypatch.setattr("simulator.clock.time.monotonic", lambda: 10)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimulationClock(at, 60, offline=True)
    monkeypatch.setattr("simulator.clock.time.monotonic", lambda: 12)
    assert clock.now() == at + timedelta(minutes=2)


@pytest.mark.parametrize(
    "profile",
    [{"charge_efficiency": Decimal(0)}, {"min_soc": Decimal(".99")}, {"latitude": 91}],
)
def test_invalid_physical_profiles_rejected(profile):
    with pytest.raises(ValueError):
        HomeProfile(**profile)


def test_checkpoint_restores_counters_soc_sequences_and_rng(tmp_path):
    from simulator.checkpoint import save, load

    home = build_home("HOME-CALI-001", "Cali", 5, 10)
    at = datetime(2026, 6, 21, 17, tzinfo=UTC)
    model = HomeEnergyModel(home, seed=7)
    model.step(at)
    model.step(at + timedelta(seconds=30))
    file = str(tmp_path / "state.json")
    save(file, {"SM-1": 17}, {home.home_id: model})
    restored = HomeEnergyModel(home, seed=999)
    sequences = {}
    load(file, sequences, {home.home_id: restored})
    assert sequences["SM-1"] == 17 and restored.counters == model.counters
    assert restored.step(at + timedelta(seconds=60)) == model.step(
        at + timedelta(seconds=60)
    )


def test_fault_injection_is_opt_in_and_does_not_mutate_original():
    from simulator.faults import inject

    rows = [
        {
            "measured_at": datetime.now(UTC).isoformat(),
            "schema_version": "1.0",
            "data": {"lifetime_energy_kwh": 5, "ac_power_w": 400},
        }
    ]
    assert len(inject(rows, "duplicate")) == 2
    assert inject(rows, "counter_reset")[0]["data"]["lifetime_energy_kwh"] == 0
    assert inject(rows, "invalid_payload")[0]["schema_version"] == "unsupported"
    assert inject(rows, "outage") == [] and rows[0]["data"]["lifetime_energy_kwh"] == 5
    with pytest.raises(ValueError):
        inject(rows, "unknown")
