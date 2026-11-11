"""Community provenance, offline clocks, profile physics and deterministic faults."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from config.homes import build_home, load_catalogue
from generators import (
    BatteryGenerator,
    SmartMeterGenerator,
    SolarInverterGenerator,
    WeatherGenerator,
)
from models.sensor import SensorType
from publishers.registered import RegisteredPublisher
from schemas.telemetry import TelemetryPayload
from simulator.coordinator import SimulationConfig, Simulator
from simulator.physics import HomeEnergyModel, profile_for

AT = datetime(2026, 11, 10, 17, tzinfo=UTC)


def generators():
    return {
        SensorType.SMART_METER: SmartMeterGenerator(False),
        SensorType.SOLAR_INVERTER: SolarInverterGenerator(False),
        SensorType.WEATHER_SENSOR: WeatherGenerator(False),
        SensorType.BATTERY_MONITOR: BatteryGenerator(False),
    }


def test_catalogue_covers_all_profiles_and_battery_integrated_conservation():
    homes, profiles = load_catalogue(
        str(Path(__file__).parents[1] / "examples/community-profiles.json")
    )
    assert len(homes) == 5 and len(
        {s.device_code for h in homes for s in h.devices}
    ) == sum(len(h.devices) for h in homes)
    assert len(homes[0].devices) == 2 and len(homes[3].devices) == 4
    model = HomeEnergyModel(homes[3], profiles[homes[3].home_id], seed=4)
    constrained = HomeEnergyModel(
        homes[3],
        profile_for("battery_prosumer", min_soc=Decimal("0.8"), max_soc=Decimal("0.9")),
        seed=4,
    )
    assert constrained.step(AT)["soc"] == 80
    initial = model.stored
    for minute in range(0, 1441, 15):
        state = model.step(AT + timedelta(minutes=minute))
        assert abs(
            state["generation"]
            + state["discharge"]
            + state["import"]
            - state["consumption"]
            - state["charge"]
            - state["export"]
        ) < Decimal("1e-18")
        assert (
            profiles[homes[3].home_id].min_soc * homes[3].battery_capacity_kwh
            <= model.stored
            <= profiles[homes[3].home_id].max_soc * homes[3].battery_capacity_kwh
        )
    energy = (
        model.counters["charge"] * model.profile.charge_efficiency
        - model.counters["discharge"] / model.profile.discharge_efficiency
    )
    assert abs(model.stored - initial - energy) < Decimal("1e-20")
    reading = model.reading("battery_monitor", AT + timedelta(days=1))
    assert (
        reading["capacity_kwh"] == 10
        and reading["cumulative_charge_energy_kwh"] == model.counters["charge"]
    )

    load = model.reading("smart_meter", AT + timedelta(days=1))
    assert load["consumption_power_w"] == model.state["consumption"]
    assert load["active_power_w"] == model.state["import"] - model.state["export"]


def test_deterministic_homes_are_independent_and_utc():
    homes, profiles = load_catalogue(
        str(Path(__file__).parents[1] / "examples/community-profiles.json")
    )
    config = SimulationConfig(
        mode="DETERMINISTIC", start=AT, speed=60, interval_seconds=15, random_seed=17
    )
    a = Simulator(homes, generators(), config=config, profiles=profiles)
    b = Simulator(reversed(homes), generators(), config=config, profiles=profiles)
    for cycle in range(3):
        first = a.simulate_cycle()
        second = b.simulate_cycle()
        assert {m["device_id"]: m for m in first} == {m["device_id"]: m for m in second}
        assert all(
            m["simulation_mode"] == "DETERMINISTIC" and m["source"] == "SIMULATED"
            for m in first
        )
        assert all(
            datetime.fromisoformat(m["measured_at"])
            == AT + timedelta(seconds=900 * cycle)
            for m in first
        )
        assert all(
            TelemetryPayload.model_validate(m).schema_version == "2.0" for m in first
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        a.simulate_cycle(datetime(2026, 11, 10))


@pytest.mark.parametrize(
    "kind", ["consumer", "solar_producer", "prosumer", "battery_prosumer", "commercial"]
)
def test_reusable_load_profiles_and_solar_curve(kind):
    profile = profile_for(kind)
    home = build_home("HOME-MS-123", "Cali", 5, 10 if kind == "battery_prosumer" else 0)
    model = HomeEnergyModel(home, profile, seed=33)
    assert model.solar_factor(datetime(2026, 11, 10, 5, tzinfo=UTC)) == 0
    assert model.solar_factor(AT) > 0.9
    day = model.step(AT)
    night = model.step(AT + timedelta(hours=12))
    assert night["generation"] == 0 and day["generation"] > 0
    assert (
        model.counters["generation"] > 0
    )  # Long elapsed time integrates the intervening sun.
    assert model.counters["consumption"] > 0
    if kind == "commercial":
        assert day["consumption"] >= profile.peak_w
    with pytest.raises(ValueError):
        profile_for("unknown")


@pytest.mark.parametrize(
    "fault",
    [
        "device_outage",
        "duplicate",
        "packet_loss",
        "counter_reset",
        "clock_drift",
        "invalid_payload",
        "export_spike",
        "unauthorized_device",
        "missing_interval",
        "out_of_order",
        "mqtt_disconnection",
    ],
)
def test_fault_matrix_is_explicit_and_reproducible(fault):
    home = build_home("HOME-MS-999", "Cali", 5, 0)
    config = SimulationConfig(
        mode="DETERMINISTIC", start=AT, random_seed=2, fault=fault
    )
    simulator = Simulator([home], generators(), config=config)
    rows = []
    for _ in range(3):
        rows.extend(simulator.simulate_cycle())
    if fault in ("device_outage", "mqtt_disconnection"):
        assert not rows
    elif fault == "duplicate":
        assert len(rows) == len(home.devices) * 6
    elif fault in ("packet_loss", "missing_interval"):
        assert len(rows) < len(home.devices) * 3
    elif fault == "counter_reset":
        assert all(
            value == 0
            for m in rows
            for field, value in m["data"].items()
            if field.endswith("_kwh")
        )
    elif fault == "invalid_payload":
        assert all(m["schema_version"] == "unsupported" for m in rows)
    elif fault == "unauthorized_device":
        assert all(m["device_id"].startswith("00000000-") for m in rows)
    elif fault == "out_of_order":
        assert rows[0]["sequence_number"] == 2 and rows[1]["sequence_number"] == 1
    else:
        assert rows
    with pytest.raises(ValueError):
        SimulationConfig(fault=fault)


def test_registry_binds_v2_community_topic_and_units(tmp_path, monkeypatch):
    home = build_home("HOME-MS-321", "Cali", 0, 0)
    message = Simulator([home], generators()).simulate_cycle(AT)[0]
    entry = {
        "device_id": "22222222-2222-4222-8222-222222222222",
        "home_id": "11111111-1111-4111-8111-111111111111",
        "community_id": "33333333-3333-4333-8333-333333333333",
        "node_id": "44444444-4444-4444-8444-444444444444",
        "credential_env": "V2_TEST_CREDENTIAL",
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({message["device_id"]: entry}))
    monkeypatch.setenv("V2_TEST_CREDENTIAL", "test-credential-at-least-32-characters")

    class Recorder:
        def publish(self, topic, payload):
            self.topic, self.payload = topic, payload

        def close(self):
            pass

    transport = Recorder()
    RegisteredPublisher(transport, str(path)).publish("ignored", message)
    assert (
        transport.topic
        == f"solar/{entry['community_id']}/{entry['node_id']}/{entry['device_id']}/telemetry"
    )
    assert transport.payload["units"]["grid_export_energy_kwh"] == "kWh"
    assert message["device_id"] != entry["device_id"]
    broken = {**message, "units": {}}
    with pytest.raises(ValueError):
        TelemetryPayload.model_validate(broken)


def test_profile_catalogue_rejects_mistakes(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('[{"home_id":"HOME-MS-123","city":"Cali","typo":4}]')
    with pytest.raises(ValueError):
        load_catalogue(str(path))
    path.write_text("[]")
    with pytest.raises(ValueError):
        load_catalogue(str(path))
    rows = [{"home_id": "HOME-MS-123", "city": "Cali"}] * 2
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError):
        load_catalogue(str(path))
