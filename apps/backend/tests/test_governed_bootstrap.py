
"""Real MQTT -> SQLModel -> native allocation/settlement -> burn/withdrawal."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import paho.mqtt.client as mqtt
import pytest
from eth_account import Account
from sqlmodel import select
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.iot.mqtt_handler import MqttIngestWorker
from src.modules.community.models import ChainOperation
from src.modules.device.models import Device, TelemetryAssessment, TelemetryMessage
from src.modules.energy.models import EnergyCredit, OutboxEvent
from src.modules.energy.processor import EnergyProcessor
from src.modules.settlement.chain import NativeSettlementChain, binary
from src.modules.settlement.models import IntervalAllocation, SettlementClaim
from src.protocol.bootstrap import bootstrap
from src.protocol.deployment import Deployment, artifacts_at
from web3 import Web3
from web3.exceptions import ContractLogicError


@pytest.mark.asyncio
async def test_governed_bootstrap_mqtt_native_lifecycle_is_idempotent(
    tmp_path, monkeypatch
):
    assert Config.MQTT_PORT == 18884 and ":18545" in Config.WEB3_PROVIDER_URL
    monkeypatch.setattr(Config, "BACKEND_PRIVATE_KEY", Account.create().key.hex())
    monkeypatch.setattr(Config, "BLOCKCHAIN_CONFIRMATION_BLOCKS", 1)
    artifacts = artifacts_at(Path(__file__).resolve().parents[3] / "contracts/out")
    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
    demo = await bootstrap(
        AsyncSessionFactory,
        w3,
        artifacts,
        tmp_path,
        "local-only-password",
        "local-device-key-" + "x" * 40,
    )
    nonce = w3.eth.get_transaction_count(demo["governance"]["address"])
    again = await bootstrap(
        AsyncSessionFactory,
        w3,
        artifacts,
        tmp_path,
        "local-only-password",
        "local-device-key-" + "x" * 40,
    )
    assert (
        demo == again
        and w3.eth.get_transaction_count(demo["governance"]["address"]) == nonce
    )
    cid = UUID(demo["community_id"])
    a, b = demo["members"][:2]
    c = {
        name: w3.eth.contract(address=demo[key], abi=artifacts[name]["abi"])
        for name, key in [
            ("CommunityRegistry", "registry"),
            ("SUNToken", "sun"),
            ("CommunitySettlement", "settlement"),
            ("NativeSettlementVault", "vault"),
        ]
    }
    sun, settlement, vault = (
        c["SUNToken"],
        c["CommunitySettlement"],
        c["NativeSettlementVault"],
    )
    assert sun.functions.totalSupply().call() == 0
    assert not sun.functions.hasRole(
        sun.functions.MINTER_ROLE().call(), demo["timelock"]
    ).call()
    bindings = dict(
        line.split("=", 1)
        for line in (tmp_path / "simulator.env").read_text().splitlines()
    )
    registry = json.loads((tmp_path / "registry.json").read_text())
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    end = end.replace(minute=end.minute // 15 * 15) - timedelta(minutes=15)
    start = end - timedelta(minutes=15)
    messages = []
    for seq, at in ((1, start), (2, end)):
        for index, number in enumerate((1, 2)):
            entry = registry[f"SM-MS-{number:03d}-001"]
            f = seq - 1
            message = {
                "schema_version": "2.0",
                "message_id": str(uuid4()),
                "source": "SIMULATED",
                "simulation_mode": "REALTIME",
                "sequence_number": seq,
                "measured_at": at.isoformat(),
                "units": {
                    key: "kWh"
                    for key in [
                        "grid_export_energy_kwh",
                        "grid_import_energy_kwh",
                        "consumption_energy_kwh",
                    ]
                },
                "sensor_type": "smart_meter",
                "credential": bindings[entry["credential_env"]],
                **{
                    key: entry[key]
                    for key in ["community_id", "node_id", "home_id", "device_id"]
                },
                "data": {
                    "grid_export_energy_kwh": 5 * f if index == 0 else 0,
                    "grid_import_energy_kwh": 3 * f if index == 1 else 0,
                    "consumption_energy_kwh": 3 * f if index == 1 else 0,
                },
            }
            messages.append(message)
    subscribed = Event()
    worker = MqttIngestWorker()
    worker._client.on_subscribe = lambda *args: subscribed.set()
    task = asyncio.create_task(worker.run())
    publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    publisher.connect(Config.MQTT_HOST, Config.MQTT_PORT)
    publisher.loop_start()
    try:
        for _ in range(100):
            if worker._client.is_connected():
                break
            await asyncio.sleep(0.05)
        assert worker._client.is_connected()
        assert await asyncio.to_thread(subscribed.wait, 5)
        invalid = {**messages[0], "message_id": str(uuid4()), "credential": "invalid"}
        for message in [invalid, *messages, *messages]:
            topic = f"solar/{message['community_id']}/{message['node_id']}/{message['device_id']}/telemetry"
            publisher.publish(topic, json.dumps(message), qos=1).wait_for_publish(
                timeout=5
            )
        ids = [UUID(x["device_id"]) for x in messages[:2]]
        for _ in range(100):
            async with AsyncSessionFactory() as db:
                devices = (
                    await db.exec(select(Device.id).where(Device.device_id.in_(ids)))
                ).all()
                rows = (
                    await db.exec(
                        select(TelemetryMessage).where(
                            TelemetryMessage.device_id.in_(devices)
                        )
                    )
                ).all()
                assessments = (
                    await db.exec(
                        select(TelemetryAssessment).where(
                            TelemetryAssessment.claimed_device_id.in_(
                                [str(x) for x in ids]
                            )
                        )
                    )
                ).all()
            if len(rows) == 4 and any(x.state == "UNAUTHORIZED" for x in assessments):
                break
            await asyncio.sleep(0.1)
        assert len(rows) == 4
        assert any(x.state == "UNAUTHORIZED" for x in assessments)
        assert all("credential" not in x.payload for x in rows)
    finally:
        publisher.disconnect()
        publisher.loop_stop()
        worker.stop()
        await task
    processor = EnergyProcessor()
    chain = NativeSettlementChain(w3)
    async with AsyncSessionFactory() as db:
        await processor.process_pending(db)
        await processor.finalize_closed_intervals(db)
        batch = await chain.service.calculate_interval(db, cid, start)
        await db.commit()
        assert (batch.injection_wh, batch.consumption_wh, batch.allocated_wh) == (
            5000,
            3000,
            3000,
        )
        assert int(batch.total_due_wei) == 3 * 10**15
        duplicate = await chain.service.calculate_interval(db, cid, start)
        assert duplicate.id == batch.id
        await db.commit()
        allocations = (
            await db.exec(
                select(IntervalAllocation).where(
                    IntervalAllocation.batch_id == batch.id
                )
            )
        ).all()
        assert len(allocations) == 1
    oracle = Account.from_key(Config.BACKEND_PRIVATE_KEY).address
    deployment = Deployment(
        w3,
        artifacts,
        tmp_path / "deployment.json",
        cid,
        demo["governance"]["address"],
        demo["governance"]["address"],
        demo["governance"]["address"],
        oracle,
    )
    deployment.deploy()
    deployment.send(vault.functions.deposit(10**15), b["address"], value=10**16)

    async def advance(rounds=8):
        for _ in range(rounds):
            async with AsyncSessionFactory() as db:
                jobs = (
                    await db.exec(
                        select(OutboxEvent).where(
                            OutboxEvent.payload["community_id"].astext == str(cid),
                            OutboxEvent.event_type.like("native.%"),
                        )
                    )
                ).all()
                for job in jobs:
                    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
                    job.locked_at = None
                await db.commit()
            await chain.process_native_outbox(AsyncSessionFactory, 100)
            w3.provider.make_request("evm_mine", [])
            async with AsyncSessionFactory() as db:
                await chain.audit_native(db, cid)
                await chain.index_native(db, cid)
                await db.commit()

    await advance()
    deployment.govern(settlement.functions.finalize(binary(batch.chain_batch_id)))
    await advance()
    assert sun.functions.balanceOf(a["address"]).call() == 5 * 10**18
    deployment.send(sun.functions.approve(vault.address, 5 * 10**18), a["address"])
    deployment.send(vault.functions.depositSUN(5 * 10**18), a["address"])
    await advance()
    assert vault.functions.earnings(a["address"]).call() == 3 * 10**15
    assert vault.functions.available(b["address"]).call() == 7 * 10**15
    assert sun.functions.balanceOf(b["address"]).call() == 3 * 10**18
    async with AsyncSessionFactory() as db:
        claim = (
            await db.exec(
                select(SettlementClaim).where(
                    SettlementClaim.batch_id == batch.id, SettlementClaim.kind == 1
                )
            )
        ).one()
        meter = await db.get(Device, claim.meter_id)
    deployment.send(sun.functions.approve(settlement.address, 3 * 10**18), b["address"])
    retirement = settlement.functions.retire(
        binary(batch.chain_batch_id),
        binary(claim.chain_claim_id),
        UUID(b["node_id"]).bytes.rjust(32, b"\0"),
        meter.device_id.bytes.rjust(32, b"\0"),
        3000,
        [binary(x) for x in claim.proof],
    )
    deployment.send(retirement, b["address"])
    with pytest.raises(ContractLogicError):
        deployment.send(retirement, b["address"])
    deployment.send(
        vault.functions.withdrawEarnings(3 * 10**15, a["address"]), a["address"]
    )
    with pytest.raises(ContractLogicError):
        deployment.send(vault.functions.withdrawEarnings(1, a["address"]), a["address"])
    await advance(2)
    assert sun.functions.totalSupply().call() == 2 * 10**18
    assert vault.functions.totalLiabilities().call() == 7 * 10**15
    assert (
        w3.eth.get_balance(vault.address) >= vault.functions.totalLiabilities().call()
    )
    assert vault.functions.earnings(a["address"]).call() == 0
    async with AsyncSessionFactory() as db:
        credits = (
            await db.exec(
                select(EnergyCredit).where(EnergyCredit.owner_id == UUID(a["user_id"]))
            )
        ).all()
        assert sum(x.energy_wh for x in credits) == 5000

    # Old signatures without a chain anchor are quarantined, never rebroadcast.
    async with AsyncSessionFactory() as db:
        job = (
            await db.exec(
                select(OutboxEvent).where(
                    OutboxEvent.payload["community_id"].astext == str(cid),
                    OutboxEvent.event_type == "native.submit",
                )
            )
        ).one()
        operation = (
            await db.exec(
                select(ChainOperation).where(ChainOperation.outbox_id == job.id)
            )
        ).one()
        assert operation.chain_genesis == chain.chain_identity()
        operation.chain_genesis = ""
        job.status = "PENDING"
        job.locked_at = None
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        job_id = job.id
        operation_id = operation.id
        await db.commit()
    await chain.process_native_outbox(AsyncSessionFactory, 100)
    async with AsyncSessionFactory() as db:
        assert (await db.get(OutboxEvent, job_id)).status == "FAILED"
        assert (await db.get(ChainOperation, operation_id)).status == "BLOCKED"
    assert sun.functions.totalSupply().call() == 2 * 10**18
