"""Marketplace business operations."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.marketplace.matching_engine import MatchingEngine
from src.modules.marketplace.models import Order
from src.modules.marketplace.repository import MarketplaceRepository
from src.modules.marketplace.schemas import OrderCreate


class MarketplaceService:
    """Create orders, run matching and expose a user's marketplace activity."""

    def __init__(self) -> None:
        self.repository = MarketplaceRepository()
        self.matcher = MatchingEngine()

    async def create_order(
        self, user, payload: OrderCreate, session: AsyncSession
    ):
        order = Order(
            creator_id=user.uid,
            order_type=payload.order_type,
            token_amount=payload.token_amount,
            price_per_token=payload.price_per_token,
            remaining_amount=payload.token_amount,
            status="OPEN",
        )
        session.add(order)
        await session.flush()
        trades = await self.matcher.match(session, order)
        await session.commit()
        await session.refresh(order)
        return {"order": order, "trades": trades}

    async def cancel_order(
        self, user, order_id: UUID, session: AsyncSession
    ):
        result = await session.exec(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
        )
        order = result.first()
        if order is None:
            raise LookupError("Order not found")
        if order.creator_id != user.uid:
            raise PermissionError("You cannot cancel another user's order")
        if order.status not in ("OPEN", "PARTIALLY_FILLED"):
            raise ValueError("Only open orders can be cancelled")
        order.status = "CANCELLED"
        order.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(order)
        return order

    async def order_book(self, session: AsyncSession):
        buys = await self.repository.list_orders(
            session, order_type="BUY", limit=100
        )
        sells = await self.repository.list_orders(
            session, order_type="SELL", limit=100
        )
        buys.sort(key=lambda item: (-item.price_per_token, item.created_at))
        sells.sort(key=lambda item: (item.price_per_token, item.created_at))
        return {"buy_orders": buys, "sell_orders": sells}

    async def my_orders(self, user, session: AsyncSession):
        return await self.repository.list_user_orders(session, user.uid)

    async def my_trades(self, user, session: AsyncSession):
        return await self.repository.list_user_trades(session, user.uid)
