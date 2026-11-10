"""Confirmation monitor for persisted EVM transactions."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.blockchain.transaction_service import TransactionService
from src.core.config import Config
from src.modules.energy.models import BlockchainTransaction, EnergyCredit
from src.modules.marketplace.models import Trade

logger = logging.getLogger(__name__)


async def monitor_submitted_transactions(
    session_factory,
    *,
    limit: int = 50,
) -> int:
    """Update transaction and energy-credit states after canonical confirmations."""
    async with session_factory() as session:
        result = await session.exec(
            select(BlockchainTransaction)
            .where(
                BlockchainTransaction.status == "SUBMITTED",
                BlockchainTransaction.transaction_hash.is_not(None),
            )
            .order_by(BlockchainTransaction.submitted_at)
            .limit(limit)
        )
        rows = list(result.all())

    if not rows:
        return 0

    service = TransactionService()
    updated = 0

    for row in rows:
        try:
            receipt = await asyncio.to_thread(
                service.get_receipt, row.transaction_hash
            )
            if receipt is None:
                continue

            async with session_factory() as session:
                async with session.begin():
                    current = await session.get(BlockchainTransaction, row.id)
                    if current is None or current.status != "SUBMITTED":
                        continue

                    # A mined revert is terminal unless an operator explicitly
                    # creates a new issuance attempt.
                    if receipt["status"] == 0:
                        current.status = "FAILED"
                        current.failure_reason = "Transaction reverted on-chain"
                        if current.entity_type == "ENERGY_CREDIT":
                            credit = await session.get(EnergyCredit, current.entity_id)
                            if credit and credit.status == "ISSUANCE_PENDING":
                                credit.status = "FAILED"
                        elif current.entity_type == "TRADE":
                            trade = await session.get(Trade, current.entity_id)
                            if trade:
                                trade.status = "FAILED"
                        updated += 1
                        continue

                    confirmations = await asyncio.to_thread(
                        service.confirmation_count, receipt
                    )
                    if confirmations < Config.BLOCKCHAIN_CONFIRMATION_BLOCKS:
                        continue

                    current.status = "CONFIRMED"
                    current.block_number = receipt["block_number"]
                    current.block_hash = receipt["block_hash"]
                    current.gas_used = receipt["gas_used"]
                    current.confirmed_at = datetime.now(timezone.utc)

                    if current.entity_type == "ENERGY_CREDIT":
                        credit = await session.get(EnergyCredit, current.entity_id)
                        if credit:
                            credit.status = "ISSUED"
                    elif current.entity_type == "TRADE":
                        trade = await session.get(Trade, current.entity_id)
                        if trade:
                            trade.status = "SETTLED"
                    updated += 1
        except Exception:
            logger.exception("Failed to monitor transaction %s", row.transaction_hash)

    return updated
