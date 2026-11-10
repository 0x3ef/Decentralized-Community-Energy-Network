"""Marketplace persistence operations."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.marketplace.models import Order, Trade


class MarketplaceRepository:
    """Query and persist orders and trades."""

    async def get_order(self, session: AsyncSession, order_id: UUID):
        return await session.get(Order, order_id)

    async def list_orders(
        self, session: AsyncSession, *, order_type: str | None = None,
        status: str = "OPEN", limit: int = 100,
    ):
        statement = select(Order).where(Order.status == status)
        if order_type:
            statement = statement.where(Order.order_type == order_type)
        statement = statement.order_by(Order.created_at).limit(limit)
        result = await session.exec(statement)
        return list(result.all())

    async def list_user_orders(
        self, session: AsyncSession, user_id: UUID, limit: int = 100
    ):
        result = await session.exec(
            select(Order)
            .where(Order.creator_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def list_user_trades(
        self, session: AsyncSession, user_id: UUID, limit: int = 100
    ):
        result = await session.exec(
            select(Trade)
            .where((Trade.buyer_id == user_id) | (Trade.seller_id == user_id))
            .order_by(Trade.created_at.desc())
            .limit(limit)
        )
        return list(result.all())
