"""Native outbox transport, confirmed event indexing and replayable projections."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import select
from src.core.config import Config
from src.modules.community.chain import CommunityChain
from src.modules.community.models import ChainOperation
from src.modules.device.models import Device
from src.modules.energy.models import EnergyCredit, OutboxEvent
from src.modules.settlement.engine import key
from src.modules.settlement.models import (
    IndexedNativeEvent,
    IntervalAllocation,
    NativeSyncCursor,
    NativeWalletTransaction,
    SettlementBatch,
    SettlementClaim,
    SettlementPolicy,
)
from src.modules.settlement.service import CommunitySettlementService
from web3 import Web3
from web3.exceptions import TransactionNotFound

logger = logging.getLogger(__name__)


def binary(hexstr):
    return Web3.to_bytes(hexstr=hexstr)


def json_value(value):
    if isinstance(value, bytes):
        return Web3.to_hex(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


class NativeSettlementChain(CommunityChain):
    def __init__(self, web3=None):
        super().__init__(web3)
        self.service = CommunitySettlementService(self)

    def confirmed_height(self):
        return max(
            0,
            self.web3.eth.block_number
            - max(1, Config.BLOCKCHAIN_CONFIRMATION_BLOCKS)
            + 1,
        )

    async def function(self, session, job):
        batch = await session.get(SettlementBatch, UUID(job.payload["batch_id"]))
        if not batch or batch.status == "RECONCILIATION_REQUIRED":
            raise ValueError("Batch requires reconciliation before new operations")
        _, deployment, _registry, settlement, vault = await self.service.contracts(
            session, batch.community_id
        )
        action = job.event_type.removeprefix("native.")
        bid = binary(batch.chain_batch_id)
        if action == "submit":
            policy = await session.get(SettlementPolicy, batch.policy_id)
            return deployment, settlement.functions.submit(
                bid,
                key(batch.community_id),
                binary(batch.root),
                int(batch.interval_start.timestamp()),
                int(batch.interval_end.timestamp()),
                binary(policy.policy_hash),
                batch.injection_wh,
                batch.consumption_wh,
                batch.allocated_wh,
            )
        if batch.status != "FINALIZED":
            raise ValueError("Governance-finalized batch required")
        if action == "issue":
            row = await session.get(SettlementClaim, job.aggregate_id)
            device = await session.get(Device, row.meter_id)
            return deployment, settlement.functions.issue(
                bid,
                binary(row.chain_claim_id),
                key(row.node_id),
                key(device.device_id),
                row.wallet,
                row.energy_wh,
                [binary(p) for p in row.proof],
            )
        row = await session.get(IntervalAllocation, job.aggregate_id)
        if action == "reserve":
            row.funding_status = await self.service.verify_funding(session, row)
            if row.funding_status != "FUNDED":
                raise ValueError(f"Allocation remains {row.funding_status}")
            return deployment, vault.functions.reserve(
                bid,
                binary(row.chain_allocation_id),
                row.producer_wallet,
                row.consumer_wallet,
                key(row.consumer_node_id),
                row.energy_wh,
                row.consumer_cap_wh,
                [binary(p) for p in row.proof],
            )
        if action == "execute":
            return deployment, vault.functions.execute(binary(row.chain_allocation_id))
        raise ValueError("Unsupported native outbox operation")

    async def process_native_outbox(self, factory, limit=20):
        count = 0
        async with factory() as session:
            ids = (
                await session.exec(
                    select(OutboxEvent.id)
                    .where(
                        OutboxEvent.event_type.like("native.%"),
                        OutboxEvent.status.in_(["PENDING", "PROCESSING"]),
                        OutboxEvent.available_at <= datetime.now(UTC),
                    )
                    .order_by(OutboxEvent.available_at)
                    .limit(limit)
                )
            ).all()
        for job_id in ids:
            try:
                # Lease and journal signature before broadcasting outside the transaction.
                async with factory() as session, session.begin():
                    job = (
                        await session.exec(
                            select(OutboxEvent)
                            .where(OutboxEvent.id == job_id)
                            .with_for_update()
                        )
                    ).one()
                    if job.status == "PROCESSED":
                        continue
                    if job.locked_at and job.locked_at > datetime.now(UTC) - timedelta(
                        seconds=30
                    ):
                        continue
                    op = (
                        await session.exec(
                            select(ChainOperation).where(
                                ChainOperation.outbox_id == job.id
                            )
                        )
                    ).first()
                    if not op:
                        deployment, function = await self.function(session, job)
                        op = await self.sign_operation(
                            session, job, function, deployment.chain_id
                        )
                    job.status = "PROCESSING"
                    job.locked_at = datetime.now(UTC)
                    await session.flush()
                    tx_hash, raw, attempts = (
                        op.transaction_hash,
                        op.raw_transaction,
                        op.previous_transactions,
                    )
                receipt = None
                for candidate in [{"hash": tx_hash, "raw": raw}, *attempts]:
                    try:
                        receipt = self.web3.eth.get_transaction_receipt(
                            candidate["hash"]
                        )
                        tx_hash, raw = candidate["hash"], candidate["raw"]
                        break
                    except TransactionNotFound:
                        pass
                if receipt is None:
                    try:
                        self.web3.eth.get_transaction(tx_hash)
                    except TransactionNotFound:
                        self.web3.eth.send_raw_transaction(binary(raw))
                else:
                    if (
                        receipt.status == 0
                        and receipt.blockNumber <= self.confirmed_height()
                        and Web3.to_hex(
                            self.web3.eth.get_block(receipt.blockNumber).hash
                        )
                        == Web3.to_hex(receipt.blockHash)
                    ):
                        async with factory() as session:
                            job = (
                                await session.exec(
                                    select(OutboxEvent)
                                    .where(OutboxEvent.id == job_id)
                                    .with_for_update()
                                )
                            ).one()
                            op = (
                                await session.exec(
                                    select(ChainOperation).where(
                                        ChainOperation.outbox_id == job.id
                                    )
                                )
                            ).one()
                            op.status = "FAILED"
                            op.block_hash = Web3.to_hex(receipt.blockHash)
                            job.status = "FAILED"
                            job.last_error = "Transaction reverted on chain; inspect the cause before explicit retry"
                            job.locked_at = None
                            await session.commit()
                        continue
                    receipt = self.canonical_receipt(tx_hash)
                    async with factory() as session, session.begin():
                        job = (
                            await session.exec(
                                select(OutboxEvent)
                                .where(OutboxEvent.id == job_id)
                                .with_for_update()
                            )
                        ).one()
                        op = (
                            await session.exec(
                                select(ChainOperation).where(
                                    ChainOperation.outbox_id == job.id
                                )
                            )
                        ).one()
                        batch = await session.get(
                            SettlementBatch, UUID(job.payload["batch_id"])
                        )
                        _, _, _, settlement, vault = await self.service.contracts(
                            session, batch.community_id
                        )
                        action = job.event_type.removeprefix("native.")
                        contract, event_name, argument, expected = {
                            "submit": (
                                settlement,
                                "BatchSubmitted",
                                "id",
                                batch.chain_batch_id,
                            ),
                            "issue": (
                                settlement,
                                "CreditClaimed",
                                "claim",
                                (
                                    await session.get(SettlementClaim, job.aggregate_id)
                                ).chain_claim_id
                                if action == "issue"
                                else "",
                            ),
                            "reserve": (
                                vault,
                                "AllocationReserved",
                                "id",
                                (
                                    await session.get(
                                        IntervalAllocation, job.aggregate_id
                                    )
                                ).chain_allocation_id
                                if action == "reserve"
                                else "",
                            ),
                            "execute": (
                                vault,
                                "AllocationSettled",
                                "id",
                                (
                                    await session.get(
                                        IntervalAllocation, job.aggregate_id
                                    )
                                ).chain_allocation_id
                                if action == "execute"
                                else "",
                            ),
                        }[action]
                        logs = self.event(contract, event_name, receipt)
                        if (
                            len(logs) != 1
                            or Web3.to_hex(logs[0].args[argument]) != expected
                        ):
                            raise ValueError(
                                "Receipt does not match native domain operation"
                            )
                        op.transaction_hash, op.raw_transaction = tx_hash, raw
                        op.status = "CONFIRMED"
                        op.block_hash = Web3.to_hex(receipt.blockHash)
                        job.status = "PROCESSED"
                        job.locked_at = None
                        count += 1
                async with factory() as session:
                    job = await session.get(OutboxEvent, job_id)
                    if job.status != "PROCESSED":
                        job.locked_at = None
                        job.available_at = datetime.now(UTC) + timedelta(seconds=2)
                    await session.commit()
            except Exception as exc:
                logger.info("Native job %s deferred: %s", job_id, type(exc).__name__)
                async with factory() as session:
                    job = (
                        await session.exec(
                            select(OutboxEvent)
                            .where(OutboxEvent.id == job_id)
                            .with_for_update()
                        )
                    ).one()
                    job.attempts += 1
                    job.last_error = str(exc)[:1000]
                    job.locked_at = None
                    job.available_at = datetime.now(UTC) + timedelta(
                        seconds=min(300, 2 ** min(job.attempts, 8))
                    )
                    await session.commit()
        return count

    async def audit_native(self, session, community_id):
        events = (
            await session.exec(
                select(IndexedNativeEvent).where(
                    IndexedNativeEvent.community_id == community_id,
                    IndexedNativeEvent.canonical.is_(True),
                )
            )
        ).all()
        hashes = {}
        reorg = False
        for event in events:
            if event.block_number not in hashes:
                try:
                    hashes[event.block_number] = Web3.to_hex(
                        self.web3.eth.get_block(event.block_number).hash
                    )
                except Exception:
                    # Missing blocks at a shorter canonical chain are reorgs; RPC outages propagate.
                    if self.web3.eth.block_number < event.block_number:
                        hashes[event.block_number] = None
                    else:
                        raise
            if hashes[event.block_number] != event.block_hash:
                event.canonical = False
                reorg = True
        ops = (
            await session.exec(
                select(ChainOperation, OutboxEvent)
                .join(OutboxEvent, OutboxEvent.id == ChainOperation.outbox_id)
                .where(
                    OutboxEvent.event_type.like("native.%"),
                    OutboxEvent.payload["community_id"].astext == str(community_id),
                    ChainOperation.status.in_(["CONFIRMED", "FAILED"]),
                )
            )
        ).all()
        for op, job in ops:
            try:
                receipt = self.web3.eth.get_transaction_receipt(op.transaction_hash)
                valid = (
                    Web3.to_hex(receipt.blockHash) == op.block_hash
                    and Web3.to_hex(self.web3.eth.get_block(receipt.blockNumber).hash)
                    == op.block_hash
                )
            except TransactionNotFound:
                valid = False
            if not valid:
                reorg = True
                op.status = "PREPARED"
                op.block_hash = None
                job.status = "PENDING"
                job.available_at = datetime.now(UTC)
                job.locked_at = None
        cursor = await session.get(NativeSyncCursor, community_id)
        if (
            cursor
            and cursor.block_number >= 0
            and (
                cursor.block_number > self.web3.eth.block_number
                or Web3.to_hex(self.web3.eth.get_block(cursor.block_number).hash)
                != cursor.block_hash
            )
        ):
            reorg = True
            cursor.block_number = -1
            cursor.block_hash = None
        if reorg:
            for batch in (
                await session.exec(
                    select(SettlementBatch).where(
                        SettlementBatch.community_id == community_id
                    )
                )
            ).all():
                batch.status = "RECONCILIATION_REQUIRED"
        return reorg

    async def index_native(self, session, community_id):
        _, deployment, registry, settlement, vault = await self.service.contracts(
            session, community_id
        )
        height = self.confirmed_height()
        expected_hash = Web3.to_hex(self.web3.eth.get_block(height).hash)
        # Replay confirmed logs. Uniqueness makes restart safe; bounded windows avoid provider range limits.
        # Persisted event rows are the cursor: always rescan the last confirmed block.
        cursor = await session.get(NativeSyncCursor, community_id)
        if cursor is None:
            cursor = NativeSyncCursor(community_id=community_id)
            session.add(cursor)
        start = max(Config.NATIVE_SETTLEMENT_START_BLOCK, cursor.block_number)
        specs = [
            (settlement, n)
            for n in (
                "BatchSubmitted",
                "BatchState",
                "CreditClaimed",
                "ConsumptionRetired",
            )
        ] + [
            (vault, n)
            for n in (
                "Deposited",
                "Withdrawn",
                "SunEscrowed",
                "AllocationReserved",
                "AllocationSettled",
                "AllocationCancelled",
            )
        ]
        specs += [
            (registry, n)
            for n in (
                "CommunityTransition",
                "MembershipChanged",
                "NodeRegistered",
                "MeterAuthorized",
                "PricePolicyConfigured",
                "ProtocolBound",
            )
        ]
        for lo in range(start, height + 1, 1000):
            hi = min(height, lo + 999)
            for contract, name in specs:
                for log in getattr(contract.events, name)().get_logs(
                    from_block=lo, to_block=hi
                ):
                    if contract.address == registry.address:
                        event_community = log.args.get(
                            "communityId", log.args.get("community")
                        )
                        if event_community != key(community_id):
                            continue
                    tx = Web3.to_hex(log.transactionHash)
                    block = Web3.to_hex(log.blockHash)
                    existing = (
                        await session.exec(
                            select(IndexedNativeEvent).where(
                                IndexedNativeEvent.chain_id == deployment.chain_id,
                                IndexedNativeEvent.transaction_hash == tx,
                                IndexedNativeEvent.log_index == log.logIndex,
                                IndexedNativeEvent.block_hash == block,
                            )
                        )
                    ).first()
                    if existing:
                        existing.canonical = True
                    else:
                        session.add(
                            IndexedNativeEvent(
                                community_id=community_id,
                                chain_id=deployment.chain_id,
                                address=contract.address,
                                transaction_hash=tx,
                                log_index=log.logIndex,
                                block_number=log.blockNumber,
                                block_hash=block,
                                event_name=name,
                                payload=json_value(dict(log.args)),
                            )
                        )
        cursor.block_number = height
        cursor.block_hash = Web3.to_hex(self.web3.eth.get_block(height).hash)
        await session.flush()
        await self.project(session, community_id, height)
        if Web3.to_hex(self.web3.eth.get_block(height).hash) != expected_hash:
            raise ValueError(
                "Canonical chain changed during native reconciliation; retry"
            )

    async def project(self, session, community_id, height):
        _, _, _, settlement, vault = await self.service.contracts(session, community_id)
        for batch in (
            await session.exec(
                select(SettlementBatch).where(
                    SettlementBatch.community_id == community_id
                )
            )
        ).all():
            state = settlement.functions.batches(binary(batch.chain_batch_id)).call(
                block_identifier=height
            )
            status = {
                0: "PREPARED",
                1: "CHALLENGEABLE",
                2: "FINALIZED",
                3: "REJECTED",
                4: "SUPERSEDED",
            }[state[11]]
            policy = await session.get(SettlementPolicy, batch.policy_id)
            if state[11] and (
                Web3.to_hex(state[2]) != batch.root
                or state[6] != batch.injection_wh
                or state[8] != batch.allocated_wh
                or state[7] != batch.consumption_wh
                or Web3.to_hex(state[1]) != policy.policy_hash
                or state[3] != int(batch.interval_start.timestamp())
                or state[4] != int(batch.interval_end.timestamp())
                or state[13] != int(policy.price_wei_per_kwh)
            ):
                raise ValueError(
                    "On-chain batch differs from immutable accounting commitment"
                )
            batch.status = (
                "RECONCILIATION_REQUIRED"
                if status == "PREPARED" and batch.status == "RECONCILIATION_REQUIRED"
                else status
            )
            for claim in (
                await session.exec(
                    select(SettlementClaim).where(SettlementClaim.batch_id == batch.id)
                )
            ).all():
                used = settlement.functions.claims(binary(claim.chain_claim_id)).call(
                    block_identifier=height
                )
                claim.status = (
                    ("ISSUED" if claim.kind == 0 else "RETIRED") if used else "ELIGIBLE"
                )
                if claim.kind == 0 and claim.energy_credit_id:
                    credit = await session.get(EnergyCredit, claim.energy_credit_id)
                    credit.status = "ISSUED" if used else "APPROVED"
            for row in (
                await session.exec(
                    select(IntervalAllocation).where(
                        IntervalAllocation.batch_id == batch.id
                    )
                )
            ).all():
                allocation = vault.functions.allocations(
                    binary(row.chain_allocation_id)
                ).call(block_identifier=height)
                row.status = {
                    0: "ELIGIBLE",
                    1: "RESERVED",
                    2: "SETTLED",
                    3: "CANCELLED",
                }[allocation[6]]
                row.funding_status = (
                    "SETTLED"
                    if row.status == "SETTLED"
                    else "FUNDED"
                    if row.status == "RESERVED"
                    else await self.service.verify_funding(session, row, height)
                )
                if batch.status == "FINALIZED":
                    await self.service.repository.enqueue(
                        session,
                        "reserve" if row.status == "ELIGIBLE" else "execute",
                        batch,
                        row.id,
                    ) if row.status in ("ELIGIBLE", "RESERVED") else None
            if batch.status == "FINALIZED":
                for claim in (
                    await session.exec(
                        select(SettlementClaim).where(
                            SettlementClaim.batch_id == batch.id,
                            SettlementClaim.kind == 0,
                            SettlementClaim.status == "ELIGIBLE",
                        )
                    )
                ).all():
                    await self.service.repository.enqueue(
                        session, "issue", batch, claim.id
                    )
        for tx in (
            await session.exec(
                select(NativeWalletTransaction).where(
                    NativeWalletTransaction.community_id == community_id
                )
            )
        ).all():
            try:
                receipt = self.web3.eth.get_transaction_receipt(tx.transaction_hash)
                canonical = Web3.to_hex(
                    self.web3.eth.get_block(receipt.blockNumber).hash
                ) == Web3.to_hex(receipt.blockHash)
                if canonical and receipt.blockNumber <= height:
                    tx.status = "CONFIRMED" if receipt.status == 1 else "FAILED"
                    tx.block_hash = Web3.to_hex(receipt.blockHash)
                else:
                    tx.status = (
                        "RECONCILIATION_REQUIRED" if tx.block_hash else "SUBMITTED"
                    )
            except TransactionNotFound:
                tx.status = "RECONCILIATION_REQUIRED" if tx.block_hash else "SUBMITTED"
