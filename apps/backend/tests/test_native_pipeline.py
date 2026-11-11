"""Real PostgreSQL/Anvil: authenticated meters -> jobs -> funded delivery -> burn."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from eth_account import Account
from httpx import ASGITransport, AsyncClient
from sqlmodel import func, select
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.iot.mqtt_handler import _insert_batch
from src.main import app
from src.modules.auth.models import User
from src.modules.auth.utils import create_access_token
from src.modules.community.models import (
    ChainOperation,
    CommunityMembership,
    CommunityNode,
    EnergyCommunity,
    MeterAuthorization,
    NativeDeployment,
)
from src.modules.device.models import Device, TelemetryMessage
from src.modules.energy.models import EnergyInterval, OutboxEvent
from src.modules.energy.processor import EnergyProcessor
from src.modules.home.models import Home
from src.modules.settlement.chain import NativeSettlementChain, binary
from src.modules.settlement.engine import hashed, key
from src.modules.settlement.models import (
    IndexedNativeEvent,
    IntervalAllocation,
    NativeWalletTransaction,
    SettlementBatch,
    SettlementClaim,
)
from src.modules.wallet.models import Wallet
from web3 import Web3


@pytest.mark.asyncio
async def test_native_pipeline_replay_crash_recovery_and_reorganization(monkeypatch):
    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
    oracle = Account.create()
    producer_wallet, consumer_wallet = (
        Account.create().address,
        Account.create().address,
    )
    for address in (oracle.address, producer_wallet, consumer_wallet):
        w3.provider.make_request("anvil_impersonateAccount", [address])
        w3.provider.make_request("anvil_setBalance", [address, hex(10**20)])
    monkeypatch.setattr(Config, "BACKEND_PRIVATE_KEY", oracle.key.hex())
    monkeypatch.setattr(Config, "BLOCKCHAIN_CONFIRMATION_BLOCKS", 1)

    def send(fn, sender=oracle.address):
        receipt = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
        assert receipt.status == 1
        return receipt

    def deploy(name, *args):
        artifact = json.loads(
            (
                Path(__file__).resolve().parents[3]
                / "contracts/out"
                / f"{name}.sol"
                / f"{name}.json"
            ).read_text()
        )
        receipt = send(
            w3.eth.contract(
                abi=artifact["abi"], bytecode=artifact["bytecode"]["object"]
            ).constructor(*args)
        )
        return w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])

    governor = deploy(
        "TimelockController", 0, [oracle.address], [oracle.address], "0x" + "0" * 40
    )
    registry = deploy("CommunityRegistry", governor.address)
    monkeypatch.setattr(Config, "GOVERNANCE_TIMELOCK_ADDRESS", governor.address)
    monkeypatch.setattr(Config, "COMMUNITY_REGISTRY_ADDRESS", registry.address)
    sequence = 0

    def govern(fn):
        nonlocal sequence
        sequence += 1
        salt = Web3.keccak(text=f"pipeline-{sequence}")
        send(
            governor.functions.schedule(
                fn.address, 0, fn._encode_transaction_data(), bytes(32), salt, 0
            )
        )
        return send(
            governor.functions.execute(
                fn.address, 0, fn._encode_transaction_data(), bytes(32), salt
            )
        )

    cid = uuid4()
    policy_hash = hashed("fixed wei 0.001 ETH/kWh; net counters; v1")
    send(
        registry.functions.propose(
            key(cid),
            Web3.keccak(text="Cali physical fixture"),
            binary(policy_hash),
            900,
        ),
        producer_wallet,
    )
    govern(registry.functions.transition(key(cid), 2, "0x" + "0" * 40))
    govern(registry.functions.transition(key(cid), 3, "0x" + "0" * 40))
    govern(registry.functions.configurePrice(key(cid), 10**15))
    activated = govern(registry.functions.transition(key(cid), 4, producer_wallet))
    sun = deploy("SUNToken", governor.address, governor.address)
    settlement = deploy(
        "CommunitySettlement",
        registry.address,
        sun.address,
        governor.address,
        1,
        key(cid),
    )
    vault = deploy(
        "NativeSettlementVault", registry.address, settlement.address, sun.address
    )
    govern(settlement.functions.bindVault(vault.address))
    govern(
        registry.functions.bindProtocol(
            key(cid), settlement.address, vault.address, sun.address
        )
    )
    govern(
        sun.functions.grantRole(sun.functions.MINTER_ROLE().call(), settlement.address)
    )
    govern(
        sun.functions.revokeRole(sun.functions.MINTER_ROLE().call(), governor.address)
    )
    govern(
        registry.functions.grantRole(
            registry.functions.ORACLE_ROLE().call(), oracle.address
        )
    )
    govern(
        registry.functions.grantRole(
            registry.functions.SETTLEMENT_ROLE().call(), oracle.address
        )
    )
    credential = "pipeline-test-meter-credential"
    users = []
    meters = []
    nodes = []
    async with AsyncSessionFactory() as db:
        for i, _wallet in enumerate((producer_wallet, consumer_wallet)):
            unique = uuid4().hex
            user = User(
                username=unique,
                email=unique + "@example.com",
                first_name="Native",
                last_name=str(i),
                password_hash="not-a-login",
            )
            db.add(user)
            await db.flush()
            users.append(user)
        unique = uuid4().hex
        governance_user = User(
            username=unique,
            email=unique + "@example.com",
            first_name="Governance",
            last_name="Proposer",
            password_hash="not-a-login",
        )
        db.add(governance_user)
        await db.flush()
        db.add(
            Wallet(
                user_id=governance_user.uid, address=oracle.address, is_verified=True
            )
        )
        community = EnergyCommunity(
            id=cid,
            name="Authorized native fixture",
            status="ACTIVE",
            proposer_id=users[0].uid,
            policy_hash=policy_hash,
            boundary_hash=Web3.to_hex(Web3.keccak(text="Cali physical fixture")),
            registry_address=registry.address,
            allow_simulated_telemetry=True,
            governance_transaction=Web3.to_hex(activated.transactionHash),
        )
        db.add(community)
        await db.flush()
        for i, (user, wallet) in enumerate(
            zip(users, (producer_wallet, consumer_wallet), strict=True)
        ):
            db.add(Wallet(user_id=user.uid, address=wallet, is_verified=True))
            db.add(
                CommunityMembership(
                    community_id=cid,
                    user_id=user.uid,
                    role="operator" if i == 0 else "member",
                    status="ACTIVE",
                )
            )
            home = Home(owner_id=user.uid, address=f"Native home {i}", city="Cali")
            db.add(home)
            await db.flush()
            node = CommunityNode(community_id=cid, home_id=home.id, authorized=True)
            db.add(node)
            await db.flush()
            nodes.append(node)
            meter = Device(
                home_id=home.id,
                device_type="smart_meter",
                telemetry_source="SIMULATED",
                mqtt_client_id=uuid4().hex,
                status="ACTIVE",
            )
            db.add(meter)
            await db.flush()
            meters.append(meter)
            db.add(
                MeterAuthorization(
                    device_id=meter.id,
                    node_id=node.id,
                    credential_hash=hashlib.sha256(credential.encode()).hexdigest(),
                )
            )
            send(registry.functions.applyMembership(key(cid)), wallet)
            govern(registry.functions.setMembership(key(cid), wallet, 2))
            govern(registry.functions.setMembership(key(cid), wallet, 3))
            govern(registry.functions.registerNode(key(cid), key(node.id), wallet))
            govern(
                registry.functions.authorizeMeter(
                    key(cid), key(node.id), key(meter.device_id), True
                )
            )
        db.add(
            NativeDeployment(
                community_id=cid,
                chain_id=31337,
                sun_address=sun.address,
                settlement_address=settlement.address,
                vault_address=vault.address,
            )
        )
        await db.commit()
        end = datetime.now(UTC).replace(second=0, microsecond=0)
        end = end.replace(minute=end.minute // 15 * 15) - timedelta(minutes=15)
        start = end - timedelta(minutes=15)
        messages = []
        for seq, at in ((1, start), (2, end)):
            for i, meter in enumerate(meters):
                f = seq - 1
                messages.append(
                    {
                        "schema_version": "2.0",
                        "message_id": str(uuid4()),
                        "community_id": str(cid),
                        "node_id": str(nodes[i].id),
                        "source": "SIMULATED",
                        "simulation_mode": "REALTIME",
                        "units": {
                            "grid_export_energy_kwh": "kWh",
                            "grid_import_energy_kwh": "kWh",
                            "consumption_energy_kwh": "kWh",
                        },
                        "device_id": str(meter.device_id),
                        "home_id": str(meter.home_id),
                        "sensor_type": "smart_meter",
                        "sequence_number": seq,
                        "measured_at": at.isoformat(),
                        "credential": credential,
                        "data": {
                            "grid_export_energy_kwh": 5 * f if i == 0 else 0,
                            "grid_import_energy_kwh": 3 * f if i == 1 else 0,
                            "consumption_energy_kwh": 3 * f if i == 1 else 0,
                        },
                    }
                )
        invalid = {**messages[0], "credential": "wrong"}
        assert await _insert_batch(db, [invalid]) == (0, 0)
        assert await _insert_batch(db, messages + messages) == (4, 4)
        await db.commit()
        processor = EnergyProcessor()
        assert await processor.process_pending(db) == 4
        await processor.finalize_closed_intervals(db)
        intervals = (
            await db.exec(
                select(EnergyInterval).where(
                    EnergyInterval.home_id.in_([m.home_id for m in meters]),
                    EnergyInterval.interval_start == start,
                )
            )
        ).all()
        assert sum(i.eligible_export_wh for i in intervals) == 5000
        assert sum(i.grid_import_wh for i in intervals) == 3000

    chain = NativeSettlementChain(w3)
    from src.modules.settlement.worker import NativeSettlementWorker

    monkeypatch.setattr(Config, "BACKEND_PRIVATE_KEY", "")
    # A finalized aggregate alone is insufficient when boundary evidence is missing.
    async with AsyncSessionFactory() as db:
        boundary = (
            await db.exec(
                select(TelemetryMessage).where(
                    TelemetryMessage.device_id == meters[0].id,
                    TelemetryMessage.measured_at == start,
                )
            )
        ).one()
        boundary.quality_status = "REJECTED"
        await db.commit()
    await NativeSettlementWorker(chain).run_once(AsyncSessionFactory)
    async with AsyncSessionFactory() as db:
        assert (
            await db.exec(
                select(func.count())
                .select_from(SettlementBatch)
                .where(SettlementBatch.community_id == cid)
            )
        ).one() == 0
        boundary = await db.get(TelemetryMessage, boundary.id)
        boundary.quality_status = "PROCESSED"
        await db.commit()
    await NativeSettlementWorker(chain).run_once(AsyncSessionFactory)
    monkeypatch.setattr(Config, "BACKEND_PRIVATE_KEY", oracle.key.hex())
    async with AsyncSessionFactory() as db:
        assert (
            await db.exec(
                select(func.count())
                .select_from(SettlementBatch)
                .where(SettlementBatch.community_id == cid)
            )
        ).one() == 1

    def headers(user):
        return {
            "Authorization": "Bearer "
            + create_access_token(
                {"email": user.email, "user_uid": str(user.uid), "role": "user"}
            )
        }

    async def reconcile():
        async with AsyncSessionFactory() as db:
            await chain.audit_native(db, cid)
            await chain.index_native(db, cid)
            await db.commit()

    async def advance_jobs(rounds=3):
        for _ in range(rounds):
            async with AsyncSessionFactory() as db:
                for job in (
                    await db.exec(
                        select(OutboxEvent).where(
                            OutboxEvent.event_type.like("native.%"),
                            OutboxEvent.payload["community_id"].astext == str(cid),
                        )
                    )
                ).all():
                    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
                    job.locked_at = None
                await db.commit()
            await chain.process_native_outbox(AsyncSessionFactory, 100)
            await reconcile()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        forbidden = await client.post(
            f"/api/v1/communities/{cid}/settlements/calculate",
            json={"interval_start": start.isoformat()},
            headers=headers(users[1]),
        )
        assert forbidden.status_code == 403

        # Concurrent API calculations serialize to a single immutable interval batch.
        async def calculate_request():
            return await client.post(
                f"/api/v1/communities/{cid}/settlements/calculate",
                json={"interval_start": start.isoformat()},
                headers=headers(users[0]),
            )

        response, parallel = await __import__("asyncio").gather(
            calculate_request(), calculate_request()
        )
        assert parallel.status_code == 200, parallel.text
        assert response.json()["id"] == parallel.json()["id"]
        assert response.status_code == 200, response.text
        batch_id = response.json()["id"]
        assert response.json()["total_due_wei"] == str(3 * 10**15)
        assert response.json()["unallocated_wh"] == 2000
        response2 = await client.post(
            f"/api/v1/communities/{cid}/settlements/calculate",
            json={"interval_start": start.isoformat()},
            headers=headers(users[0]),
        )
        assert response2.json()["id"] == batch_id
        # Signature journal survives a crash before its first broadcast.
        async with AsyncSessionFactory() as db:
            job = (
                await db.exec(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == __import__("uuid").UUID(batch_id)
                    )
                )
            ).one()
            dep, fn = await chain.function(db, job)
            op = await chain.sign_operation(db, job, fn, dep.chain_id)
            await db.commit()
            original_hash = op.transaction_hash
            with pytest.raises(
                __import__(
                    "web3.exceptions", fromlist=["TransactionNotFound"]
                ).TransactionNotFound
            ):
                w3.eth.get_transaction(original_hash)
        await advance_jobs()
        async with AsyncSessionFactory() as db:
            batch = await db.get(SettlementBatch, __import__("uuid").UUID(batch_id))
            assert batch.status == "CHALLENGEABLE"
            assert (
                await db.exec(
                    select(ChainOperation).where(ChainOperation.outbox_id == job.id)
                )
            ).one().transaction_hash == original_hash
        w3.provider.make_request("evm_increaseTime", [2])
        w3.provider.make_request("evm_mine", [])
        govern(settlement.functions.finalize(binary(batch.chain_batch_id)))
        await reconcile()
        await advance_jobs()
        assert sun.functions.balanceOf(producer_wallet).call() == 5 * 10**18
        async with AsyncSessionFactory() as db:
            allocation = (
                await db.exec(
                    select(IntervalAllocation).where(
                        IntervalAllocation.batch_id == batch.id
                    )
                )
            ).one()
            assert (
                allocation.status == "ELIGIBLE"
                and allocation.funding_status == "UNFUNDED"
            )

        async def user_action(index, action, amount="0", **extra):
            response = await client.post(
                f"/api/v1/communities/{cid}/native/prepare",
                json={"action": action, "amount_base_units": str(amount), **extra},
                headers=headers(users[index]),
            )
            assert response.status_code == 200, response.text
            prepared = response.json()
            receipt = w3.eth.wait_for_transaction_receipt(
                w3.eth.send_transaction(
                    {
                        "from": (producer_wallet, consumer_wallet)[index],
                        "to": prepared["to"],
                        "data": prepared["data"],
                        "value": int(prepared["value"]),
                    }
                )
            )
            assert receipt.status == 1
            tracked = await client.post(
                f"/api/v1/communities/{cid}/native/transactions",
                json={
                    "transaction_hash": Web3.to_hex(receipt.transactionHash),
                    "action": action,
                },
                headers=headers(users[index]),
            )
            assert tracked.status_code == 202, tracked.text
            assert tracked.json()["status"] in ("SUBMITTED", "RECONCILIATION_REQUIRED")
            return receipt

        await user_action(1, "deposit", 10**15)
        await advance_jobs(1)
        assert vault.functions.earnings(producer_wallet).call() == 0
        await user_action(1, "deposit", 9 * 10**15)
        await user_action(0, "approve_sun", 3 * 10**18)
        await user_action(0, "escrow_sun", 3 * 10**18)
        # Funding may change between preflight and mining. A mined revert is
        # terminal, retains its nonce/history and needs an explicit new job.
        async with AsyncSessionFactory() as db:
            reserve_job = (
                await db.exec(
                    select(OutboxEvent).where(
                        OutboxEvent.event_type == "native.reserve",
                        OutboxEvent.aggregate_id == allocation.id,
                    )
                )
            ).one()
            dep, fn = await chain.function(db, reserve_job)
            failed_operation = await chain.sign_operation(
                db, reserve_job, fn, dep.chain_id
            )
            await db.commit()
        await user_action(1, "withdraw", 10**16)
        await advance_jobs(2)
        async with AsyncSessionFactory() as db:
            assert (
                await db.get(ChainOperation, failed_operation.id)
            ).status == "FAILED"
            assert (await db.get(OutboxEvent, reserve_job.id)).status == "FAILED"
        assert vault.functions.earnings(producer_wallet).call() == 0
        retry = await client.post(
            f"/api/v1/communities/{cid}/settlements/{batch.id}/jobs/{reserve_job.id}/retry",
            headers=headers(users[0]),
        )
        assert retry.status_code == 202, retry.text
        assert retry.json()["job_id"] != str(reserve_job.id)
        await user_action(1, "deposit", 10**16)

        await advance_jobs(
            1
        )  # reserve is broadcast; confirmation/delivery remain separate
        assert vault.functions.reserved(consumer_wallet).call() == 3 * 10**15
        snapshot = w3.provider.make_request("evm_snapshot", [])["result"]
        await advance_jobs(3)
        assert vault.functions.earnings(producer_wallet).call() == 3 * 10**15
        assert sun.functions.balanceOf(consumer_wallet).call() == 3 * 10**18
        await advance_jobs(2)
        assert vault.functions.earnings(producer_wallet).call() == 3 * 10**15
        async with AsyncSessionFactory() as db:
            claim = (
                await db.exec(
                    select(SettlementClaim).where(
                        SettlementClaim.batch_id == batch.id, SettlementClaim.kind == 1
                    )
                )
            ).one()
        view = await client.get(
            f"/api/v1/communities/{cid}/settlements/{batch.id}/claims?kind=1",
            headers=headers(users[1]),
        )
        assert view.status_code == 200, view.text
        assert view.json()[0]["retirement_eligible"] is True
        assert view.json()[0]["chain_meter_id"] == Web3.to_hex(key(meters[1].device_id))
        policy_view = await client.get(
            f"/api/v1/communities/{cid}/settlement-policy", headers=headers(users[1])
        )
        assert policy_view.status_code == 200, policy_view.text
        assert policy_view.json()["price_wei_per_kwh"] == str(10**15)
        funding_view = await client.get(
            f"/api/v1/communities/{cid}/allocations/{allocation.id}/funding",
            headers=headers(users[1]),
        )
        assert funding_view.status_code == 200, funding_view.text
        assert funding_view.json()["status"] == "SETTLED"
        assert funding_view.json()["available_sun_units"] is None
        private_claims = await client.get(
            f"/api/v1/communities/{cid}/settlements/{batch.id}/claims?kind=0",
            headers=headers(users[1]),
        )
        assert private_claims.status_code == 200 and private_claims.json() == []
        hidden_jobs = await client.get(
            f"/api/v1/communities/{cid}/settlements/{batch.id}/operations",
            headers=headers(users[1]),
        )
        assert hidden_jobs.status_code == 403

        await user_action(1, "approve_retirement", 3 * 10**18)
        retire_args = {
            "batch_id": batch.chain_batch_id,
            "claim_id": claim.chain_claim_id,
            "node_id": Web3.to_hex(key(nodes[1].id)),
            "meter_id": Web3.to_hex(key(meters[1].device_id)),
            "proof": claim.proof,
        }
        before = vault.functions.earnings(producer_wallet).call()
        await user_action(1, "retire", 3000, **retire_args)
        await reconcile()
        assert vault.functions.earnings(producer_wallet).call() == before
        assert sun.functions.balanceOf(consumer_wallet).call() == 0
        duplicate = await client.post(
            f"/api/v1/communities/{cid}/native/prepare",
            json={"action": "retire", "amount_base_units": "3000", **retire_args},
            headers=headers(users[1]),
        )
        assert duplicate.status_code in (422, 409), duplicate.text
        statement = await client.get(
            f"/api/v1/communities/{cid}/settlement-statement", headers=headers(users[0])
        )
        assert statement.status_code == 200, statement.text
        assert statement.json()["claimable_wei"] == str(3 * 10**15)
        # Replay indexes without duplicate events or payments.
        async with AsyncSessionFactory() as db:
            count = (
                await db.exec(
                    select(func.count())
                    .select_from(IndexedNativeEvent)
                    .where(IndexedNativeEvent.community_id == cid)
                )
            ).one()
        await reconcile()
        async with AsyncSessionFactory() as db:
            assert (
                await db.exec(
                    select(func.count())
                    .select_from(IndexedNativeEvent)
                    .where(IndexedNativeEvent.community_id == cid)
                )
            ).one() == count
        assert w3.provider.make_request("evm_revert", [snapshot])["result"]
        await reconcile()
        async with AsyncSessionFactory() as db:
            assert (await db.get(SettlementClaim, claim.id)).status == "ELIGIBLE"
            assert (
                await db.get(IntervalAllocation, allocation.id)
            ).status == "RESERVED"
            assert (
                await db.exec(
                    select(func.count())
                    .select_from(IndexedNativeEvent)
                    .where(
                        IndexedNativeEvent.community_id == cid,
                        IndexedNativeEvent.canonical.is_(False),
                    )
                )
            ).one() > 0
            orphan = (
                await db.exec(
                    select(NativeWalletTransaction).where(
                        NativeWalletTransaction.community_id == cid,
                        NativeWalletTransaction.action == "retire",
                    )
                )
            ).one()
            assert orphan.status == "RECONCILIATION_REQUIRED"
        await advance_jobs(3)
        assert vault.functions.earnings(producer_wallet).call() == 3 * 10**15
        await user_action(1, "approve_retirement", 3 * 10**18)
        await user_action(1, "retire", 3000, **retire_args)
        await reconcile()
        await user_action(0, "withdraw_earnings", 3 * 10**15)
        await reconcile()
        paid_statement = await client.get(
            f"/api/v1/communities/{cid}/settlement-statement", headers=headers(users[0])
        )
        assert paid_statement.status_code == 200, paid_statement.text
        assert paid_statement.json()["withdrawn_earnings_wei"] == str(3 * 10**15)
        assert paid_statement.json()["claimable_wei"] == "0"
        assert vault.functions.earnings(producer_wallet).call() == 0
        assert vault.functions.totalLiabilities().call() == 7 * 10**15
        assert sun.functions.totalSupply().call() == 2 * 10**18
        unauthorized = await client.post(
            f"/api/v1/communities/{cid}/governance/prepare",
            json={"action": "transition", "status": 5},
            headers=headers(users[0]),
        )
        assert unauthorized.status_code == 403
        proposal = await client.post(
            f"/api/v1/communities/{cid}/governance/prepare",
            json={"action": "transition", "status": 5},
            headers=headers(governance_user),
        )
        assert proposal.status_code == 200, proposal.text
        proposal = proposal.json()
        assert proposal["status"] == "AWAITING_GOVERNANCE_EXECUTION"
        assert registry.functions.isActive(key(cid)).call() is True
        for operation in ("schedule", "execute"):
            tx = proposal[operation]
            executed = w3.eth.wait_for_transaction_receipt(
                w3.eth.send_transaction(
                    {
                        "from": oracle.address,
                        "to": tx["to"],
                        "data": tx["data"],
                        "value": 0,
                    }
                )
            )
            assert executed.status == 1
            if operation == "schedule":
                assert registry.functions.isActive(key(cid)).call() is True
        synced = await client.post(
            f"/api/v1/communities/{cid}/governance/sync",
            json={"transaction_hash": Web3.to_hex(executed.transactionHash)},
            headers=headers(governance_user),
        )
        assert synced.status_code == 200, synced.text
        assert synced.json()["status"] == "SUSPENDED"
