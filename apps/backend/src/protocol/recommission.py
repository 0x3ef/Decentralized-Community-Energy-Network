"""Recommission a missing, unused local deployment without replacing SQL data."""

import asyncio
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlmodel import select
from web3 import Web3

from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.modules.community.models import (
    ChainDeployment,
    ChainOperation,
    CommunityEnergyAllocation,
    CommunityEnergyLedger,
    CommunityNode,
    CompensationRequest,
    EnergyCommunity,
    NativeDeployment,
    SettlementObligation,
)
from src.modules.energy.models import EnergyCredit, EnergyInterval, OutboxEvent
from src.modules.settlement.models import (
    IndexedNativeEvent,
    NativeSyncCursor,
    NativeWalletTransaction,
    SettlementBatch,
)
from src.protocol.deployment import artifacts_at, save_json


class RecommissionError(ValueError):
    """A fixed guard message safe to show without provider details."""


GOVERNANCE_EVENTS = (
    "CommunityTransition",
    "MembershipChanged",
    "NodeRegistered",
    "MeterAuthorized",
    "PricePolicyConfigured",
    "ProtocolBound",
)


async def assert_recommission_allowed(db, web3, artifacts, community_id):
    if (
        Config.ENVIRONMENT != "development"
        or Config.CHAIN_ID not in (31337, 1337)
        or web3.eth.chain_id != Config.CHAIN_ID
    ):
        raise RecommissionError(
            "Recommissioning is restricted to local development Anvil"
        )
    community = await db.get(EnergyCommunity, community_id)
    if not community or not community.registry_address or community.status != "ACTIVE":
        raise RecommissionError(
            "An existing active local demo with a missing registry is required"
        )
    if web3.eth.get_code(community.registry_address):
        raise RecommissionError(
            "Registry still exists; normal startup must not replace it"
        )
    # Even pending batches/references need review: never interpret them as proof
    # that no payment was made on the missing chain.
    for model in (
        SettlementBatch,
        NativeWalletTransaction,
        ChainDeployment,
        CommunityEnergyAllocation,
        CommunityEnergyLedger,
        CompensationRequest,
        SettlementObligation,
    ):
        count = (
            await db.exec(
                select(func.count())
                .select_from(model)
                .where(model.community_id == community_id)
            )
        ).one()
        if count:
            raise RecommissionError(
                f"Financial/history records exist in {model.__tablename__}; no database data was changed. Explicit reconciliation is required"
            )
    financial_event = (
        await db.exec(
            select(IndexedNativeEvent.id)
            .where(
                IndexedNativeEvent.community_id == community_id,
                IndexedNativeEvent.event_name.notin_(GOVERNANCE_EVENTS),
            )
            .limit(1)
        )
    ).first()
    if financial_event:
        raise RecommissionError(
            "Indexed settlement/funding events require explicit reconciliation"
        )
    jobs = select(OutboxEvent.id).where(
        OutboxEvent.payload["community_id"].astext == str(community_id)
    )
    operation = (
        await db.exec(
            select(ChainOperation.id).where(ChainOperation.outbox_id.in_(jobs)).limit(1)
        )
    ).first()
    native_job = (
        await db.exec(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.payload["community_id"].astext == str(community_id),
                OutboxEvent.event_type.like("native.%"),
            )
            .limit(1)
        )
    ).first()
    if operation or native_job:
        raise RecommissionError(
            "Existing signed/native operations require explicit reconciliation"
        )
    approved = (
        await db.exec(
            select(EnergyCredit.id)
            .join(EnergyInterval, EnergyInterval.id == EnergyCredit.interval_id)
            .join(CommunityNode, CommunityNode.home_id == EnergyInterval.home_id)
            .where(
                CommunityNode.community_id == community_id,
                EnergyCredit.status.notin_(["PENDING", "REJECTED"]),
            )
            .limit(1)
        )
    ).first()
    if approved:
        raise RecommissionError(
            "Approved or issued credits require explicit reconciliation"
        )
    native = await db.get(NativeDeployment, community_id)
    if native:
        if native.chain_id != Config.CHAIN_ID:
            raise RecommissionError(
                "Stored deployment belongs to another chain; no bindings were changed"
            )
        if web3.eth.get_code(native.sun_address):
            sun = web3.eth.contract(
                address=native.sun_address, abi=artifacts["SUNToken"]["abi"]
            )
            if sun.functions.totalSupply().call():
                raise RecommissionError(
                    "Existing SUN supply prevents empty-deployment recommissioning"
                )
        if web3.eth.get_balance(native.vault_address):
            raise RecommissionError(
                "Existing vault funds prevent empty-deployment recommissioning"
            )
    cursor = await db.get(NativeSyncCursor, community_id)
    return {
        "community_id": str(community_id),
        "registry": community.registry_address,
        "native_deployment": native.model_dump(mode="json") if native else None,
        "cursor": cursor.model_dump(mode="json") if cursor else None,
        "governance_event_ids": [
            str(value)
            for value in (
                await db.exec(
                    select(IndexedNativeEvent.id).where(
                        IndexedNativeEvent.community_id == community_id,
                        IndexedNativeEvent.event_name.in_(GOVERNANCE_EVENTS),
                    )
                )
            ).all()
        ],
        "genesis": Web3.to_hex(web3.eth.get_block(0).hash),
    }


async def recommission(factory, web3, artifacts, output, password, device_key):
    from src.protocol.bootstrap import bootstrap, identifier

    output = Path(output)
    scenario = output / "scenario.json"
    if (output / "scenario-report.json").exists() or (
        scenario.exists() and json.loads(scenario.read_text()).get("actions")
    ):
        raise RecommissionError(
            "Existing scenario transaction history requires explicit reconciliation; no database data was changed"
        )
    async with factory() as db:
        before = await assert_recommission_allowed(
            db, web3, artifacts, identifier("community")
        )
    archive = output / ("recommission-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S%f"))
    archive.mkdir(mode=0o700, parents=True)
    save_json(archive / "old-binding.json", before)
    for name in (
        "deployment.json",
        "demo.json",
        "scenario.json",
        "scenario-report.json",
    ):
        source = output / name
        if source.exists():
            shutil.copy2(source, archive / name)
    if scenario.exists():
        scenario.unlink()  # archived; no participant transaction was recorded
    if (output / "deployment.json").exists():
        (output / "deployment.json").unlink()  # archived; financial guard has passed
    # Preserve wallet keys, user passwords, meter credentials, telemetry and counters.
    public = await bootstrap(
        factory, web3, artifacts, output, password, device_key, recommission=True
    )
    save_json(archive / "new-binding.json", public)
    print(
        "Local contracts commissioned on the SAME database. Users, homes, devices, telemetry and credentials were preserved."
    )
    return public


async def main():
    await recommission(
        AsyncSessionFactory,
        Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL)),
        artifacts_at(os.environ.get("CONTRACT_ARTIFACT_DIR", "/artifacts")),
        Path(os.environ.get("DEMO_OUTPUT_DIR", "/run/demo")),
        os.environ.get("SEED_PASSWORD", ""),
        os.environ.get("SEED_DEVICE_KEY", ""),
    )


if __name__ == "__main__":
    # Bootstrap imports this module by package name. Use that same module's
    # exception class when invoked with -m, rather than a duplicate __main__ class.
    from src.protocol.recommission import RecommissionError as GuardError
    from src.protocol.recommission import main as canonical_main

    try:
        asyncio.run(canonical_main())
    except GuardError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        raise SystemExit(
            f"Recommissioning stopped ({type(error).__name__}); retained SQL data and archived bindings require review."
        ) from None
