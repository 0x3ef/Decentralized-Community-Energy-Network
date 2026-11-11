"""Canonical SQLModel seed and real energy persistence, without fabricated credits."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import func, select
from src.core.db import AsyncSessionFactory
from src.iot.mqtt_handler import _insert_batch
from src.modules.auth.models import User
from src.modules.auth.utils import verify_password
from src.modules.community.models import MeterAuthorization
from src.modules.device.models import Device
from src.modules.energy.models import EnergyCredit, EnergyInterval
from src.modules.energy.processor import EnergyProcessor
from src.modules.home.models import Home
from src.modules.wallet.models import Wallet
from src.seed import identifier, seed_demo


@pytest.mark.asyncio
async def test_seed_is_idempotent_preserves_security_and_matches_simulator_models():
    async with AsyncSessionFactory() as db:
        async with db.begin():
            first = await seed_demo(
                db, "seed-test-password-only", "seed-test-device-key-at-least-32-chars"
            )
        device_ids = {row["device_id"] for row in first["registry"].values()}
        before = (
            await db.exec(select(Device).where(Device.device_id.in_(device_ids)))
        ).all()
        assert len(before) == 15
        home_ids = {row["home_id"] for row in first["registry"].values()}
        homes = (await db.exec(select(Home).where(Home.id.in_(home_ids)))).all()
        assert sorted(h.installed_capacity_w for h in homes) == [0, 0, 3000, 4000, 6000]
        assert all(
            h.country == "Colombia" and h.timezone == "America/Bogota" for h in homes
        )
        owner = await db.get(User, homes[0].owner_id)
        old_hash = owner.password_hash
        assert verify_password("seed-test-password-only", old_hash)
        wallet = (
            await db.exec(select(Wallet).where(Wallet.user_id == owner.uid))
        ).one()
        assert not wallet.is_verified
        # Reruns must not silently reset a password or reactivate a revoked meter.
        authorization = await db.get(MeterAuthorization, before[0].id)
        authorization.active = False
        await db.commit()
        second = await seed_demo(
            db, "another-seed-password", "seed-test-device-key-at-least-32-chars"
        )
        await db.commit()
        assert second == first
        await db.refresh(owner)
        await db.refresh(authorization)
        assert owner.password_hash == old_hash and not authorization.active
        assert (
            len(
                (
                    await db.exec(
                        select(Device).where(Device.device_id.in_(device_ids))
                    )
                ).all()
            )
            == 15
        )
        # Explicitly restore the fixture's authorization, not via seeding.
        authorization.active = True
        await db.commit()


@pytest.mark.asyncio
async def test_seeded_physical_readings_create_only_observed_export_eligibility(
    monkeypatch,
):
    from config.homes import build_default_homes
    from generators import (
        BatteryGenerator,
        SmartMeterGenerator,
        SolarInverterGenerator,
        WeatherGenerator,
    )
    from models.sensor import SensorType
    from publishers.registered import RegisteredPublisher
    from simulator.coordinator import SimulationConfig, Simulator
    from simulator.physics import HomeEnergyModel

    # Isolated clear-sky fixture removes weather/time-of-day dependence. Daily
    # solar variation is tested separately against the real solar model.
    monkeypatch.setattr(HomeEnergyModel, "solar_factor", lambda self, at: 1)
    async with AsyncSessionFactory() as db:
        plan = await seed_demo(
            db, "seed-test-password-only", "seed-test-device-key-at-least-32-chars"
        )
        await db.commit()

        from src.modules.community.models import EnergyCommunity

        fixture_community = await db.get(EnergyCommunity, identifier("community"))
        assert fixture_community.status == "DRAFT"
        fixture_community.status = (
            "ACTIVE"  # Accounting-only fixture; no API governance bypass.
        )
        await db.commit()

        class RecordingTransport:
            def __init__(self):
                self.messages = []

            def publish(self, topic, message):
                self.messages.append({**message, "_mqtt_topic": topic})

            def close(self):
                pass

        transport = RecordingTransport()
        # Reuse the real registry adapter without writing device secrets to disk.
        adapter = RegisteredPublisher.__new__(RegisteredPublisher)
        adapter.publisher = transport
        adapter.registry = plan["registry"]
        for name, value in plan["bindings"].items():
            monkeypatch.setenv(name, value)
        generators = {
            SensorType.SMART_METER: SmartMeterGenerator(False),
            SensorType.SOLAR_INVERTER: SolarInverterGenerator(False),
            SensorType.WEATHER_SENSOR: WeatherGenerator(False),
            SensorType.BATTERY_MONITOR: BatteryGenerator(False),
        }
        sim = Simulator(
            build_default_homes(),
            generators,
            adapter,
            SimulationConfig(
                sequence_offset=int(datetime.now(UTC).timestamp() * 1000),
                random_seed=42,
            ),
        )
        end = datetime.now(UTC).replace(second=0, microsecond=0)
        end = end.replace(minute=end.minute // 15 * 15) - timedelta(minutes=15)
        start = end - timedelta(minutes=15)

        # Exercise the production REALTIME scheduling path from an unaligned
        # process start. The clock advances instead of sleeping for 15 minutes.
        class Clock:
            at = start - timedelta(seconds=4, microseconds=137)

            def now(self):
                return self.at

        clock = Clock()

        class Stop:
            def is_set(self):
                return clock.at > end

            def wait(self, seconds):
                clock.at += timedelta(seconds=seconds)

        sim._clock = clock
        sim.run(Stop())
        count = 61 * 15
        assert len(transport.messages) == count
        inserted, duplicates = await _insert_batch(
            db, transport.messages + transport.messages
        )
        assert (inserted, duplicates) == (count, count)
        await db.commit()
        processor = EnergyProcessor()
        await processor.process_pending(db, limit=count)
        await processor.finalize_closed_intervals(db)
        producer_home = next(
            row["home_id"]
            for code, row in plan["registry"].items()
            if code == "SM-MS-002-001"
        )
        consumer_home = next(
            row["home_id"]
            for code, row in plan["registry"].items()
            if code == "SM-MS-003-001"
        )
        producer = (
            await db.exec(
                select(EnergyInterval).where(
                    EnergyInterval.home_id == producer_home,
                    EnergyInterval.interval_start == start,
                )
            )
        ).one()
        consumer = (
            await db.exec(
                select(EnergyInterval).where(
                    EnergyInterval.home_id == consumer_home,
                    EnergyInterval.interval_start == start,
                )
            )
        ).one()
        exported = next(
            m["data"]["grid_export_energy_kwh"]
            for m in transport.messages
            if m["home_id"] == producer_home
            and m["sensor_type"] == "smart_meter"
            and m["sequence_number"] == sim._sequence_numbers["SM-MS-002-001"]
        )
        assert producer.eligible_export_wh == round(Decimal(exported) * 1000) > 0
        assert consumer.grid_import_wh > 0 and consumer.eligible_export_wh == 0
        assert producer.quality_status == consumer.quality_status == "FINALIZED"
        credit = (
            await db.exec(
                select(EnergyCredit).where(EnergyCredit.interval_id == producer.id)
            )
        ).one()
        assert (
            credit.energy_wh == producer.eligible_export_wh
            and credit.status == "PENDING"
        )
        assert await _insert_batch(db, transport.messages) == (0, count)
        await db.commit()
        await processor.process_pending(db)
        await processor.finalize_closed_intervals(db)
        assert (
            await db.exec(
                select(func.count())
                .select_from(EnergyCredit)
                .where(EnergyCredit.interval_id == producer.id)
            )
        ).one() == 1


def test_seed_registers_all_mapper_relationships_in_a_fresh_python_process():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.seed; from sqlalchemy.orm import configure_mappers; configure_mappers()",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
