"""Real PostgreSQL and Anvil: authorized measurement through payment and burn."""

import json
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import pytest
from eth_account import Account
from sqlalchemy.exc import DBAPIError
from sqlmodel import select
from web3 import Web3
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.modules.auth.models import User
from src.modules.home.models import Home
from src.modules.device.models import Device, TelemetryMessage
from src.modules.wallet.models import Wallet
from src.modules.energy.models import EnergyCredit, EnergyInterval
from src.modules.energy.processor import EnergyProcessor
from src.modules.community.models import (
    CommunityMembership,
    ChainDeployment,
    CompensationRequest,
    ChainOperation,
)
from src.modules.community.service import CommunityService
from src.modules.community.chain import CommunityChain
from src.iot.mqtt_handler import _insert_batch, MqttIngestWorker

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_full_community_lifecycle():
    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
    assert w3.eth.chain_id == 31337
    signer = Account.create()
    Config.BACKEND_PRIVATE_KEY = signer.key.hex()
    Config.BLOCKCHAIN_CONFIRMATION_BLOCKS = 1
    admin = signer.address
    seller, buyer = Account.create().address, Account.create().address
    for address in (admin, seller, buyer):
        w3.provider.make_request("anvil_impersonateAccount", [address])
        w3.provider.make_request("anvil_setBalance", [address, hex(10**20)])

    def send(fn, sender=admin):
        receipt = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
        assert receipt.status == 1
        return receipt

    def deploy(name, *args):
        artifact = json.loads(
            (ROOT / "contracts" / "out" / f"{name}.sol" / f"{name}.json").read_text()
        )
        receipt = send(
            w3.eth.contract(
                abi=artifact["abi"], bytecode=artifact["bytecode"]["object"]
            ).constructor(*args)
        )
        return w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])

    svc = CommunityService()
    chain = CommunityChain(w3)
    unique = uuid4().hex
    async with AsyncSessionFactory() as db:
        producer = User(
            username="p" + unique,
            email=f"p{unique}@example.com",
            first_name="P",
            last_name="Demo",
            password_hash="not-a-login",
        )
        consumer = User(
            username="c" + unique,
            email=f"c{unique}@example.com",
            first_name="C",
            last_name="Demo",
            password_hash="not-a-login",
        )
        db.add_all([producer, consumer])
        await db.flush()
        community = await svc.create(db, producer, "Demo " + unique)
        # Isolate legacy accounting tests from registry synchronization tests.
        community.status = "ACTIVE"
        proposer_membership = (
            await db.exec(
                select(CommunityMembership).where(
                    CommunityMembership.community_id == community.id,
                    CommunityMembership.user_id == producer.uid,
                )
            )
        ).one()
        proposer_membership.status = "ACTIVE"
        proposer_membership.role = "operator"
        db.add(CommunityMembership(community_id=community.id, user_id=consumer.uid))
        h1 = Home(
            owner_id=producer.uid, address="Producer", city="Cali", has_battery=True
        )
        h2 = Home(owner_id=consumer.uid, address="Consumer", city="Cali")
        db.add_all([h1, h2])
        await db.flush()
        n1 = await svc.register_node(db, producer, community.id, h1.id)
        n2 = await svc.register_node(db, producer, community.id, h2.id)
        meters = [
            Device(
                home_id=h1.id, device_type="smart_meter", mqtt_client_id="p" + unique
            ),
            Device(
                home_id=h2.id, device_type="smart_meter", mqtt_client_id="c" + unique
            ),
            Device(
                home_id=h1.id, device_type="solar_inverter", mqtt_client_id="s" + unique
            ),
        ]
        meters.append(
            Device(
                home_id=h1.id,
                device_type="battery_monitor",
                mqtt_client_id="b" + unique,
            )
        )
        db.add_all(meters)
        await db.flush()
        credential = "meter-credential-at-least-32-" + unique
        for meter, node in zip(meters, (n1, n2, n1, n1)):
            await svc.authorize_meter(db, producer, node.id, meter.id, credential)
        # These test wallets are unlocked only on the disposable Anvil network.
        # Actual clients link wallets using a signed nonce challenge.
        db.add_all(
            [
                Wallet(user_id=producer.uid, address=seller, is_verified=True),
                Wallet(user_id=consumer.uid, address=buyer, is_verified=True),
            ]
        )
        sun = deploy("SUNToken", admin, admin)
        usd = deploy("MockUSD", admin)
        ref = community.id.bytes.rjust(32, b"\0")
        market = deploy("EnergyMarketplace", sun.address, usd.address, ref, admin)
        retirement = deploy("EnergyCompensation", sun.address, ref, admin)
        db.add(
            ChainDeployment(
                community_id=community.id,
                chain_id=31337,
                sun_address=sun.address,
                payment_address=usd.address,
                marketplace_address=market.address,
                compensation_address=retirement.address,
            )
        )
        await db.commit()
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        end = end.replace(minute=end.minute // 15 * 15) - timedelta(minutes=15)
        start = end - timedelta(minutes=15)

        def envelope(meter, seq, at, data):
            return dict(
                schema_version="1.0",
                device_id=str(meter.device_id),
                home_id=str(meter.home_id),
                sensor_type=meter.device_type,
                sequence_number=seq,
                measured_at=at.isoformat(),
                data=data,
                credential=credential,
            )

        messages = []
        for seq, at in ((1, start), (2, end)):
            f = seq - 1
            messages.extend(
                [
                    envelope(
                        meters[0],
                        seq,
                        at,
                        dict(
                            grid_export_energy_kwh=5 * f,
                            grid_import_energy_kwh=0,
                            consumption_energy_kwh=6 * f,
                        ),
                    ),
                    envelope(
                        meters[1],
                        seq,
                        at,
                        dict(
                            grid_export_energy_kwh=0,
                            grid_import_energy_kwh=3 * f,
                            consumption_energy_kwh=3 * f,
                        ),
                    ),
                    envelope(meters[2], seq, at, dict(lifetime_energy_kwh=10 * f)),
                    envelope(
                        meters[3],
                        seq,
                        at,
                        dict(charge_power_w=0, discharge_power_w=4000),
                    ),
                ]
            )
        # Exercise the actual MQTT subscriber and its post-commit QoS1 ack.
        import paho.mqtt.client as mqtt
        from sqlalchemy import func

        worker = MqttIngestWorker()
        subscribed = asyncio.Event()
        loop = asyncio.get_running_loop()
        worker._client.on_subscribe = lambda *args: loop.call_soon_threadsafe(
            subscribed.set
        )
        task = asyncio.create_task(worker.run())
        publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        try:
            await asyncio.wait_for(subscribed.wait(), timeout=10)
            publisher.connect(Config.MQTT_HOST, Config.MQTT_PORT)
            publisher.loop_start()
            for payload in messages + messages:
                topic = f"solar/{payload['home_id']}/{payload['device_id']}/telemetry"
                info = publisher.publish(topic, json.dumps(payload), qos=1)
                await asyncio.to_thread(info.wait_for_publish, 10)
            for attempt in range(50):
                async with AsyncSessionFactory() as check:
                    total = (
                        await check.exec(
                            select(func.count())
                            .select_from(TelemetryMessage)
                            .where(
                                TelemetryMessage.device_id.in_([m.id for m in meters])
                            )
                        )
                    ).one()
                if total == 8:
                    break
                await asyncio.sleep(0.1)
            assert total == 8, (
                "Real MQTT subscriber must durably persist all meter samples"
            )
        finally:
            publisher.disconnect()
            publisher.loop_stop()
            worker.stop()
            await asyncio.wait_for(task, timeout=10)
        assert await _insert_batch(db, messages) == (0, 8)
        await db.commit()
        assert await _insert_batch(
            db, [{**messages[-1], "sequence_number": 3, "credential": "wrong"}]
        ) == (0, 0)
        await db.commit()
        spoofed = {
            **messages[0],
            "sequence_number": 99,
            "_mqtt_topic": "solar/other/unknown/telemetry",
        }
        assert await _insert_batch(db, [spoofed]) == (0, 0)
        await db.commit()
        processor = EnergyProcessor()
        assert await processor.process_pending(db) >= 8
        await processor.finalize_closed_intervals(db)
        credit = (
            await db.exec(
                select(EnergyCredit).where(EnergyCredit.owner_id == producer.uid)
            )
        ).one()
        assert credit.energy_wh == 5000 and credit.token_amount == Decimal(5)
        await svc.approve_credit(db, producer, credit.id)
        await db.commit()
        late = {
            **messages[0],
            "sequence_number": 3,
            "measured_at": (start + timedelta(minutes=1)).isoformat(),
        }
        assert await _insert_batch(db, [late]) == (1, 0)
        await db.commit()
        await processor.process_pending(db)
        rejected = (
            await db.exec(
                select(TelemetryMessage).where(
                    TelemetryMessage.device_id == meters[0].id,
                    TelemetryMessage.sequence_number == 3,
                )
            )
        ).one()
        assert rejected.quality_status == "REJECTED"
    snapshot = w3.provider.make_request("evm_snapshot", [])["result"]
    w3.provider.make_request("evm_setAutomine", [False])
    try:
        await chain.process_outbox(AsyncSessionFactory)
        from src.modules.energy.models import OutboxEvent

        async with AsyncSessionFactory() as replacement_session:
            operation = (
                await replacement_session.exec(
                    select(ChainOperation)
                    .join(OutboxEvent, OutboxEvent.id == ChainOperation.outbox_id)
                    .where(
                        OutboxEvent.aggregate_id == credit.id,
                        OutboxEvent.event_type == "community.credit.issue",
                    )
                )
            ).one()
            previous_hash, previous_nonce = operation.transaction_hash, operation.nonce
            await chain.replace_pending(replacement_session, operation.id)
            await replacement_session.commit()
            assert (
                operation.nonce == previous_nonce
                and operation.transaction_hash != previous_hash
            )
            assert operation.previous_transactions[0]["hash"] == previous_hash
        await chain.process_outbox(AsyncSessionFactory)
        w3.provider.make_request("evm_mine", [])
    finally:
        w3.provider.make_request("evm_setAutomine", [True])
    for _ in range(3):
        await asyncio.gather(
            chain.process_outbox(AsyncSessionFactory),
            chain.process_outbox(AsyncSessionFactory),
        )
    async with AsyncSessionFactory() as db:
        credit = await db.get(EnergyCredit, credit.id)
        assert credit.status == "ISSUED"
        assert sun.functions.balanceOf(seller).call() == 5 * 10**18
        source = await db.get(EnergyInterval, credit.interval_id)
        assert source.battery_discharge_wh == 1000 and source.battery_charge_wh == 0
        withdrawal = (
            await db.exec(
                select(EnergyInterval).where(
                    EnergyInterval.home_id == h2.id,
                    EnergyInterval.interval_start == start,
                )
            )
        ).one()
        send(market.functions.setMember(seller, True))
        send(market.functions.setMember(buyer, True))
        send(usd.functions.faucet(buyer, 2000 * 10**6))
        send(sun.functions.approve(market.address, 3 * 10**18), seller)
        send(
            market.functions.placeSellOrder(
                3 * 10**18, 450 * 10**6, w3.eth.get_block("latest").timestamp + 3600
            ),
            seller,
        )
        send(usd.functions.approve(market.address, 1350 * 10**6), buyer)
        trade = send(market.functions.fillOrder(0, 3 * 10**18), buyer)
        trade_hash = Web3.to_hex(trade.transactionHash)
        payments = await chain.reconcile_trade(db, consumer, community.id, trade_hash)
        assert len(payments) == 1 and payments[0].payment_units == 1350 * 10**6
        assert (await chain.reconcile_trade(db, consumer, community.id, trade_hash))[
            0
        ].id == payments[0].id
        other = await svc.create(db, consumer, "Other community " + unique)
        other.status = "ACTIVE"
        other_member = (
            await db.exec(
                select(CommunityMembership).where(
                    CommunityMembership.community_id == other.id,
                    CommunityMembership.user_id == consumer.uid,
                )
            )
        ).one()
        other_member.status = "ACTIVE"
        with pytest.raises(ValueError, match="community"):
            await svc.reserve_compensation(
                db,
                consumer,
                other.id,
                source.id,
                withdrawal.id,
                1000,
                "cross-community-" + unique,
            )
        await db.commit()

        async def competing_reservation():
            async with AsyncSessionFactory() as competing:
                row = await svc.reserve_compensation(
                    competing,
                    consumer,
                    community.id,
                    source.id,
                    withdrawal.id,
                    3000,
                    "compensate-" + unique,
                )
                await competing.commit()
                return row.id

        first, second = await asyncio.gather(
            competing_reservation(), competing_reservation()
        )
        assert first == second
        request = await db.get(CompensationRequest, first)
        assert (
            await svc.reserve_compensation(
                db,
                consumer,
                community.id,
                source.id,
                withdrawal.id,
                3000,
                "compensate-" + unique,
            )
        ).id == request.id
        await db.commit()
        with pytest.raises(ValueError, match="withdrawal"):
            await svc.reserve_compensation(
                db,
                consumer,
                community.id,
                source.id,
                withdrawal.id,
                1,
                "duplicate-" + unique,
            )
    for _ in range(3):
        await asyncio.gather(
            chain.process_outbox(AsyncSessionFactory),
            chain.process_outbox(AsyncSessionFactory),
        )
    async with AsyncSessionFactory() as db:
        request = await db.get(CompensationRequest, request.id)
        assert request.status == "AUTHORIZED"
        send(sun.functions.approve(retirement.address, 3 * 10**18), buyer)
        burn = send(
            retirement.functions.retire(Web3.keccak(text=str(request.id))), buyer
        )
        burn_hash = Web3.to_hex(burn.transactionHash)
        await chain.sync_events(AsyncSessionFactory)
        await db.refresh(request)
        assert request.status == "CONFIRMED"
        await chain.confirm_retirement(db, consumer, request.id, burn_hash)
        await db.commit()
        assert (
            await chain.confirm_retirement(db, consumer, request.id, burn_hash)
        ).status == "CONFIRMED"
        statement = await svc.statement(db, consumer, community.id)
        assert statement["compensated_wh"] == 3000 and statement["allocated_wh"] == 3000
        assert sun.functions.accountingAnchors(
            Web3.keccak(text=str(credit.id))
        ).call() != bytes(32)
        assert sun.functions.totalSupply().call() == 2 * 10**18
        assert (
            sun.functions.balanceOf(seller).call() == 2 * 10**18
            and sun.functions.balanceOf(buyer).call() == 0
        )
        assert (
            usd.functions.balanceOf(seller).call() == 1350 * 10**6
            and usd.functions.balanceOf(buyer).call() == 650 * 10**6
        )
        request_id, credit_id = request.id, credit.id
        from sqlalchemy import text

        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "UPDATE community_energy_ledger SET energy_wh=0 WHERE community_id=:id"
                ),
                {"id": community.id},
            )
        await db.rollback()

    assert w3.provider.make_request("evm_revert", [snapshot])["result"]
    await chain.audit_confirmed(AsyncSessionFactory)
    async with AsyncSessionFactory() as db:
        assert (
            await db.get(CompensationRequest, request_id)
        ).status == "RECONCILIATION"
        assert (await db.get(EnergyCredit, credit_id)).status == "FAILED"
