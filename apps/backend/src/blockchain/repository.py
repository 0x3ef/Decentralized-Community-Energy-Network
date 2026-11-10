"""Persistence helpers for blockchain transaction records."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.energy.models import BlockchainTransaction


class BlockchainRepository:
    """Database access for blockchain transaction records."""

    async def get_by_idempotency_key(
        self, session: AsyncSession, key: str
    ) -> BlockchainTransaction | None:
        result = await session.exec(
            select(BlockchainTransaction).where(
                BlockchainTransaction.idempotency_key == key
            )
        )
        return result.first()

    async def get_pending(
        self, session: AsyncSession, limit: int = 100
    ) -> list[BlockchainTransaction]:
        result = await session.exec(
            select(BlockchainTransaction)
            .where(
                BlockchainTransaction.status == "SUBMITTED",
                BlockchainTransaction.transaction_hash.is_not(None),
            )
            .order_by(BlockchainTransaction.submitted_at)
            .limit(limit)
        )
        return list(result.all())

    async def mark_submitted(
        self,
        session: AsyncSession,
        transaction_id: UUID,
        result: dict,
    ) -> BlockchainTransaction:
        tx = await session.get(BlockchainTransaction, transaction_id)
        if tx is None:
            raise LookupError("Blockchain transaction record not found")
        tx.transaction_hash = result["transaction_hash"]
        tx.sender = result["sender"]
        tx.nonce = result["nonce"]
        tx.chain_id = result["chain_id"]
        tx.status = "SUBMITTED"
        tx.submitted_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(tx)
        return tx
