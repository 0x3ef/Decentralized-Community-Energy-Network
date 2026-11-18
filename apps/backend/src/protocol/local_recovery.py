"""Explicit local-chain replacement on the SAME database; retain every row.

Historical financial records are archived from active projections, never replayed
or reported as balances of the new chain. Original states are retained in an audit
record. Host orchestration takes a full SQL backup before invoking this module.
"""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select
from web3 import Web3

from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.modules.community.models import (
    ChainOperation,
    EnergyCommunity,
    NativeDeployment,
)
from src.modules.device.models import DeviceCounterSnapshot
from src.modules.energy.models import OutboxEvent
from src.modules.settlement.models import (
    IndexedNativeEvent,
    LocalChainRecovery,
    NativeSyncCursor,
    NativeWalletTransaction,
    SettlementBatch,
)
from src.protocol.bootstrap import (
    bootstrap,
    identifier,
    local_accounts,
    verify_existing_identity,
)
from src.protocol.deployment import artifacts_at, save_json


class RecoveryError(ValueError):
    """Fixed operational guidance safe to display without provider payloads."""


def local_only(web3):
    if (
        Config.ENVIRONMENT != "development"
        or Config.CHAIN_ID != 31337
        or web3.eth.chain_id != 31337
    ):
        raise RecoveryError("Local recovery requires development Anvil chain 31337")
    if Config.LEGACY_SETTLEMENT_ENABLED:
        raise RecoveryError("Disable legacy settlement before native local recovery")


async def pending(session, web3):
    return (
        await session.exec(
            select(LocalChainRecovery).where(
                LocalChainRecovery.community_id == identifier("community"),
                LocalChainRecovery.new_genesis
                == Web3.to_hex(web3.eth.get_block(0).hash),
            )
        )
    ).first()


async def assert_pending_recovery(factory, web3):
    local_only(web3)
    async with factory() as session:
        record = await pending(session, web3)
        if not record or record.status != "PREPARED":
            raise RecoveryError("An explicit prepared local recovery audit is required")


async def export_scenario_baseline(session, output, native):
    baseline = {}
    for number in (1, 2):
        code = f"SM-MS-{number:03d}-001"
        snapshots = (
            await session.exec(
                select(DeviceCounterSnapshot).where(
                    DeviceCounterSnapshot.device_id == identifier("device:" + code)
                )
            )
        ).all()
        baseline[code] = {row.counter_name: row.counter_value_wh for row in snapshots}
    save_json(
        output / "scenario-baseline.json",
        {
            "accounting_start": native.accounting_start.isoformat(),
            "meters": baseline,
        },
    )


async def recover(factory, web3, artifacts, output, password, device_key):
    local_only(web3)
    try:
        await verify_existing_identity(factory, local_accounts(device_key), password)
    except ValueError as error:
        raise RecoveryError(str(error)) from None
    cid = identifier("community")
    output = Path(output)
    async with factory() as session:
        # Writers are stopped by the host; this lock also serializes accidental duplicate invocations.
        from src.modules.settlement.repository import SettlementRepository

        await SettlementRepository().lock(session, "local-chain-recovery")
        record = await pending(session, web3)
        if record and record.status == "COMPLETED":
            if not (output / "scenario-baseline.json").exists():
                await export_scenario_baseline(
                    session, output, await session.get(NativeDeployment, cid)
                )
            return record.details["new_binding"]
        if record is None:
            community = await session.get(EnergyCommunity, cid)
            native = await session.get(NativeDeployment, cid)
            if not community or not native or not community.registry_address:
                raise RecoveryError(
                    "Existing governed database required; use make setup for a fresh installation"
                )
            if web3.eth.get_code(community.registry_address):
                raise RecoveryError(
                    "Registry still exists; recovery will not replace a live protocol"
                )
            if community.status != "ACTIVE":
                raise RecoveryError(
                    "Existing community is not active; explicit governance review required"
                )
            record = LocalChainRecovery(
                community_id=cid,
                new_genesis=Web3.to_hex(web3.eth.get_block(0).hash),
                details={
                    "old_binding": native.model_dump(mode="json"),
                    "old_community": community.model_dump(mode="json"),
                    "old_registry": community.registry_address,
                    "notice": "Lost local chain archived. No previous payment, SUN supply or retirement was recreated.",
                },
            )
            before = dict(record.details)
            for model, label, query in (
                (
                    SettlementBatch,
                    "batches",
                    select(SettlementBatch).where(SettlementBatch.community_id == cid),
                ),
                (
                    NativeWalletTransaction,
                    "wallet_transactions",
                    select(NativeWalletTransaction).where(
                        NativeWalletTransaction.community_id == cid
                    ),
                ),
                (
                    IndexedNativeEvent,
                    "events",
                    select(IndexedNativeEvent).where(
                        IndexedNativeEvent.community_id == cid
                    ),
                ),
                (
                    OutboxEvent,
                    "jobs",
                    select(OutboxEvent).where(
                        OutboxEvent.payload["community_id"].astext == str(cid),
                        OutboxEvent.event_type.like("native.%"),
                    ),
                ),
            ):
                rows = (await session.exec(query)).all()
                before[label] = [
                    {
                        "id": str(row.id),
                        "status": getattr(row, "status", None),
                        "canonical": getattr(row, "canonical", None),
                    }
                    for row in rows
                ]
                for row in rows:
                    if model is SettlementBatch or model is NativeWalletTransaction:
                        row.archived = True
                        row.status = "RECONCILIATION_REQUIRED"
                    elif model is IndexedNativeEvent:
                        row.canonical = False
                    elif row.status != "DONE":
                        row.status = "FAILED"
                        row.locked_at = None
                        row.last_error = "Archived local chain; replay prohibited"
            ops = (
                await session.exec(
                    select(ChainOperation)
                    .join(OutboxEvent, OutboxEvent.id == ChainOperation.outbox_id)
                    .where(
                        OutboxEvent.payload["community_id"].astext == str(cid),
                        OutboxEvent.event_type.like("native.%"),
                    )
                )
            ).all()
            before["operations"] = [
                {"id": str(op.id), "status": op.status} for op in ops
            ]
            for op in ops:
                op.status = "ARCHIVED"
            cursor = await session.get(NativeSyncCursor, cid)
            before["cursor"] = cursor.model_dump(mode="json") if cursor else None
            if cursor:
                cursor.block_number, cursor.block_hash = -1, None
            record.details = before
            session.add(record)
            await session.commit()
    public = await bootstrap(
        factory, web3, artifacts, output, password, device_key, recovering=True
    )
    async with factory() as session:
        record = await pending(session, web3)
        native = await session.get(NativeDeployment, cid)
        now = datetime.now(UTC)
        native.accounting_start = datetime.fromtimestamp(
            (int(now.timestamp()) // 900 + 1) * 900, UTC
        )
        record.details = {
            **record.details,
            "new_binding": public,
            "accounting_start": native.accounting_start.isoformat(),
        }
        await export_scenario_baseline(session, output, native)
        record.status = "COMPLETED"
        await session.commit()
        save_json(output / "last-recovery.json", record.model_dump(mode="json"))
    print(
        "Local chain recommissioned on the SAME database. All records retained; historical financial records archived without replay."
    )
    return public


async def main():
    await recover(
        AsyncSessionFactory,
        Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL)),
        artifacts_at(os.environ.get("CONTRACT_ARTIFACT_DIR", "/artifacts")),
        Path(os.environ.get("DEMO_OUTPUT_DIR", "/run/demo")),
        os.environ.get("SEED_PASSWORD", ""),
        os.environ.get("SEED_DEVICE_KEY", ""),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RecoveryError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        print(
            f"Local recovery stopped ({type(error).__name__}); SQL records and recovery audit retained."
        )
        raise SystemExit(1) from None
