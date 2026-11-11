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
from src.modules.settlement.models import SettlementBatch, NativeWalletTransaction

logger = logging.getLogger(__name__)


class NativeSettlementWorker:
    def __init__(self, chain=None):
        self.chain = chain or NativeSettlementChain()
        self._unavailable = set()

    async def run_once(self, factory):
        async with factory() as session:
            communities = (
                await session.exec(select(NativeDeployment.community_id))
            ).all()
        for community_id in communities:
            try:
                async with factory() as session:
                    deployment = await session.get(NativeDeployment, community_id)
                    community = await session.get(EnergyCommunity, community_id)
                    addresses = (
                        community.registry_address,
                        deployment.sun_address,
                        deployment.settlement_address,
                        deployment.vault_address,
                    )
                    if not all(
                        address and self.chain.web3.eth.get_code(address)
                        for address in addresses
                    ):
                        # A reset/wrong chain must not leave historical confirmations
                        # presented as currently canonical or trigger fresh payments.
                        await self.chain.service.repository.lock(
                            session, f"native-reconcile:{community_id}"
                        )
                        for batch in (
                            await session.exec(
                                select(SettlementBatch).where(
                                    SettlementBatch.community_id == community_id
                                )
                            )
                        ).all():
                            batch.status = "RECONCILIATION_REQUIRED"
                        for transaction in (
                            await session.exec(
                                select(NativeWalletTransaction).where(
                                    NativeWalletTransaction.community_id
                                    == community_id,
                                    NativeWalletTransaction.status == "CONFIRMED",
                                )
                            )
                        ).all():
                            transaction.status = "RECONCILIATION_REQUIRED"
                        await session.commit()
                        if community_id not in self._unavailable:
                            logger.warning(
                                "native_deployment_unavailable: %s", community_id
                            )
                            self._unavailable.add(community_id)
                        continue
                    self._unavailable.discard(community_id)
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
