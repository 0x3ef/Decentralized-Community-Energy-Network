"""Versioned community meter evidence and conservative interval quality."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.iot.mqtt_handler import _insert_batch
from src.iot.telemetry_validator import measurement_unit
from src.main import app
from src.modules.auth.models import User
from src.modules.auth.utils import create_access_token
from src.modules.community.models import (
    CommunityMembership,
    CommunityNode,
    EnergyCommunity,
    MeterAuthorization,
)
from src.modules.device.models import Device, TelemetryAssessment
from src.modules.energy.models import EnergyCredit, EnergyInterval
from src.modules.energy.processor import EnergyProcessor
from src.modules.home.models import Home


async def fixture(db):
    unique = uuid4().hex
    user = User(
        username=unique,
        email=unique + "@example.com",
        first_name="Quality",
        last_name="Test",
        password_hash="not-a-login",
    )
    db.add(user)
    await db.flush()
    community = EnergyCommunity(
        name="Opted-in local simulation",
        proposer_id=user.uid,
        status="ACTIVE",
        allow_simulated_telemetry=True,
    )
    home = Home(owner_id=user.uid, address="Physical test point", city="Cali")
    db.add_all([community, home])
    await db.flush()
    db.add(
        CommunityMembership(
            community_id=community.id,
            user_id=user.uid,
            status="ACTIVE",
            role="operator",
        )
    )
    node = CommunityNode(community_id=community.id, home_id=home.id, authorized=True)
    device = Device(
        home_id=home.id,
        device_type="smart_meter",
        telemetry_source="SIMULATED",
        mqtt_client_id=unique,
        status="ACTIVE",
    )
    db.add_all([node, device])
    await db.flush()
    credential = "test-only-device-credential-at-least-32"
    db.add(
        MeterAuthorization(
            device_id=device.id,
            node_id=node.id,
            credential_hash=hashlib.sha256(credential.encode()).hexdigest(),
        )
    )
    await db.commit()
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    end = end.replace(minute=end.minute // 15 * 15) - timedelta(minutes=15)
    start = end - timedelta(minutes=15)

    def message(seq, at, export, **overrides):
        data = {
            "grid_export_energy_kwh": str(export),
            "grid_import_energy_kwh": "0",
            "consumption_energy_kwh": "0",
        }
        return {
            "schema_version": "2.0",
            "message_id": str(uuid4()),
            "community_id": str(community.id),
            "node_id": str(node.id),
            "home_id": str(home.id),
            "device_id": str(device.device_id),
            "sensor_type": "smart_meter",
            "sequence_number": seq,
            "measured_at": at.isoformat(),
            "source": "SIMULATED",
            "simulation_mode": "REALTIME",
            "units": {k: measurement_unit(k) for k in data},
            "data": data,
            "credential": credential,
            "_mqtt_topic": f"solar/{community.id}/{node.id}/{device.device_id}/telemetry",
            **overrides,
        }

    return user, community, device, start, end, message


@pytest.mark.asyncio
async def test_v2_identity_units_audit_duplicates_and_owned_health():
    async with AsyncSessionFactory() as db:
        user, _community, device, start, end, message = await fixture(db)
        first = message(1, start, 0)
        second = message(2, end, 5)
        assert await _insert_batch(db, [first, second, first, second]) == (2, 2)
        # A reused message ID cannot add a new delta through a different sequence.
        assert await _insert_batch(db, [{**second, "sequence_number": 3}]) == (0, 1)
        await db.commit()
        await EnergyProcessor().process_pending(db)
        await EnergyProcessor().finalize_closed_intervals(db)
        interval = (
            await db.exec(
                select(EnergyInterval).where(
                    EnergyInterval.home_id == device.home_id,
                    EnergyInterval.interval_start == start,
                )
            )
        ).one()
        assert (
            interval.quality_status == "FINALIZED"
            and interval.eligible_export_wh == 5000
        )
        assert (
            await db.exec(
                select(EnergyCredit).where(EnergyCredit.interval_id == interval.id)
            )
        ).one().status == "PENDING"
        before = device.last_seen_at
        assert await _insert_batch(
            db, [message(4, end, 100, credential="incorrect")]
        ) == (0, 0)
        assert await _insert_batch(
            db, [message(5, end, 100, community_id=str(uuid4()))]
        ) == (0, 0)
        assert await _insert_batch(
            db, [message(6, end, 100, units={"grid_export_energy_kwh": "Wh"})]
        ) == (0, 0)
        await db.commit()
        await db.refresh(device)
        assert device.last_seen_at == before
        bad = message(7, end, -1)
        await _insert_batch(db, [bad])
        await db.commit()
        await db.refresh(interval)
        assert interval.quality_status == "DISPUTED"
        assert (
            await db.exec(
                select(EnergyCredit).where(EnergyCredit.interval_id == interval.id)
            )
        ).one().status == "REJECTED"
        from types import SimpleNamespace

        from src.modules.settlement.chain import NativeSettlementChain

        with pytest.raises(ValueError, match="requires review"):
            await NativeSettlementChain().validate_source(
                db,
                SimpleNamespace(
                    evidence={"measurements": [{"interval_id": str(interval.id)}]}
                ),
            )

        token = create_access_token(
            {"email": user.email, "user_uid": str(user.uid), "role": "user"}
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": "Bearer " + token},
        ) as client:
            health = await client.get(f"/api/v1/iot/devices/{device.id}/health")
            assert health.status_code == 200, health.text
            assert health.json()["quality_counts"]["DUPLICATE"] == 3
            assert health.json()["quality_counts"]["UNAUTHORIZED"] == 2
            evidence = await client.get(f"/api/v1/iot/devices/{device.id}/quality")
            assert evidence.status_code == 200
            assert "test-only-device-credential" not in evidence.text
            assert "incorrect" not in evidence.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    ["offline", "unknown_field", "range", "overflow", "stale", "source", "sepolia"],
)
async def test_invalid_provenance_or_values_never_make_energy(fault, monkeypatch):
    async with AsyncSessionFactory() as db:
        _, community, device, start, end, message = await fixture(db)
        first = message(1, start, 0)
        bad = message(2, end, 5)
        if fault == "offline":
            bad["simulation_mode"] = "ACCELERATED"
        if fault == "unknown_field":
            bad["data"]["invented_energy_kwh"] = "500"
            bad["units"]["invented_energy_kwh"] = "kWh"
        if fault == "range":
            bad["data"]["grid_export_energy_kwh"] = "-1"
        if fault == "overflow":
            bad["data"]["grid_export_energy_kwh"] = "1e100"
        if fault == "stale":
            bad["measured_at"] = (start - timedelta(days=2)).isoformat()
        if fault == "source":
            bad["source"] = "PHYSICAL"
        if fault == "sepolia":
            monkeypatch.setattr(Config, "CHAIN_ID", 11155111)
        await _insert_batch(db, [first, bad])
        await db.commit()
        await EnergyProcessor().process_pending(db)
        await EnergyProcessor().finalize_closed_intervals(db)
        assert not (
            await db.exec(
                select(EnergyCredit).where(
                    EnergyCredit.owner_id == community.proposer_id
                )
            )
        ).all()
        assessments = (
            await db.exec(
                select(TelemetryAssessment).where(
                    TelemetryAssessment.claimed_device_id == str(device.device_id)
                )
            )
        ).all()
        assert any(row.state in ("INVALID", "STALE") for row in assessments)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reset", "gap", "rollover", "spike", "out_of_order"])
async def test_counter_quality_and_configured_rollover(kind):
    async with AsyncSessionFactory() as db:
        _, community, device, start, end, message = await fixture(db)
        first = message(
            1,
            start,
            Decimal("9.9") if kind == "rollover" else 5 if kind == "reset" else 0,
        )
        if kind == "rollover":
            device.counter_modulus_wh = 10000
            await db.commit()
        await _insert_batch(db, [first])
        await db.commit()
        await EnergyProcessor().process_pending(db)
        if kind == "out_of_order":
            bad = message(2, start - timedelta(seconds=1), 1)
        elif kind == "gap":
            bad = message(2, end + timedelta(minutes=15), 1)
        else:
            bad = message(
                2,
                end,
                Decimal("0.1")
                if kind == "rollover"
                else 1
                if kind == "reset"
                else 1000000,
            )
        await _insert_batch(db, [bad])
        await db.commit()
        await EnergyProcessor().process_pending(db)
        await EnergyProcessor().finalize_closed_intervals(db)
        rows = (
            await db.exec(
                select(EnergyCredit).where(
                    EnergyCredit.owner_id == community.proposer_id
                )
            )
        ).all()
        if kind == "rollover":
            assert len(rows) == 1 and rows[0].energy_wh == 200
        else:
            assert not rows
            expected = {
                "reset": "COUNTER_RESET",
                "gap": "COUNTER_GAP",
                "spike": "SUSPECT",
                "out_of_order": "OUT_OF_ORDER",
            }[kind]
            assert (
                await db.exec(
                    select(TelemetryAssessment).where(
                        TelemetryAssessment.device_id == device.id,
                        TelemetryAssessment.state == expected,
                    )
                )
            ).first()


@pytest.mark.asyncio
async def test_network_callbacks_are_bounded_before_the_event_loop_drains(monkeypatch):
    import asyncio
    import json
    from types import SimpleNamespace

    from src.iot.mqtt_handler import MqttIngestWorker

    monkeypatch.setattr(Config, "QUEUE_MAXSIZE", 1)
    worker = MqttIngestWorker()
    payload = json.dumps({"device_id": str(uuid4()), "data": {}}).encode()
    for mid in (1, 2, 3):
        worker._on_message(
            worker._client,
            None,
            SimpleNamespace(
                topic="solar/test/device/telemetry", payload=payload, mid=mid, qos=1
            ),
        )
    await asyncio.sleep(0)
    assert worker._queue.qsize() == 1
    assert worker._overflowed is True
