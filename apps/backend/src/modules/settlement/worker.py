"""Autonomous calculations and reconciliation, without governance impersonation."""

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import select
from src.core.config import Config
from src.modules.community.models import (
    CommunityNode,
    EnergyCommunity,
    NativeDeployment,
)
from src.modules.energy.models import EnergyInterval
from src.modules.settlement.chain import NativeSettlementChain
from src.modules.settlement.models import SettlementBatch

logger = logging.getLogger(__name__)


class NativeSettlementWorker:
    def __init__(self, chain=None):
        self.chain = chain or NativeSettlementChain()

    async def run_once(self, factory):
        async with factory() as session:
            communities = (
                await session.exec(select(NativeDeployment.community_id))
            ).all()
        for community_id in communities:
            try:
                async with factory() as session:
                    await self.chain.service.repository.lock(
                        session, f"native-reconcile:{community_id}"
                    )
                    await self.chain.audit_native(session, community_id)
                    await self.chain.index_native(session, community_id)
                    await session.commit()
                async with factory() as session:
                    community = await session.get(EnergyCommunity, community_id)
                    if community.status != "ACTIVE":
                        continue
                    starts = (
                        await session.exec(
                            select(EnergyInterval.interval_start)
                            .outerjoin(
                                SettlementBatch,
                                (SettlementBatch.community_id == community_id)
                                & (
                                    SettlementBatch.interval_start
                                    == EnergyInterval.interval_start
                                )
                                & (
                                    SettlementBatch.interval_end
                                    == EnergyInterval.interval_end
                                ),
                            )
                            .join(
                                CommunityNode,
                                CommunityNode.home_id == EnergyInterval.home_id,
                            )
                            .where(
                                CommunityNode.community_id == community_id,
                                SettlementBatch.id.is_(None),
                                EnergyInterval.quality_status == "FINALIZED",
                                EnergyInterval.interval_end
                                <= datetime.now(UTC) - timedelta(minutes=2),
                                EnergyInterval.interval_start
                                >= datetime.now(UTC)
                                - timedelta(
                                    hours=Config.NATIVE_SETTLEMENT_LOOKBACK_HOURS
                                ),
                            )
                            .distinct()
                            .order_by(EnergyInterval.interval_start.desc())
                            .limit(Config.NATIVE_SETTLEMENT_INTERVAL_LIMIT)
                        )
                    ).all()
                for start in starts:
                    try:
                        async with factory() as session:
                            await self.chain.service.calculate_interval(
                                session, community_id, start
                            )
                            await session.commit()
                    except (ValueError, PermissionError):
                        logger.debug(
                            "Native interval not eligible: %s %s", community_id, start
                        )
            except Exception:
                logger.exception(
                    "Native community reconciliation failed: %s", community_id
                )
        if Config.BACKEND_PRIVATE_KEY:
            await self.chain.process_native_outbox(factory)
