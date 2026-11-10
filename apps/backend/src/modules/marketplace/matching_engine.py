"""Deterministic price-time matching for the off-chain order book."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.marketplace.models import Order, Trade


class MatchingEngine:
    """Match a newly submitted order against the opposite side.

    Price-time priority:
      * BUY taker: lowest compatible SELL price first.
      * SELL taker: highest compatible BUY price first.
      * Older orders win when prices are equal.

    The database transaction must wrap this method so order decrements and
    trade creation commit atomically. Trade.order_id references the SELL order,
    matching the original database schema.
    """

    async def match(self, session: AsyncSession, taker: Order) -> list[Trade]:
        if taker.status not in ("OPEN", "PARTIALLY_FILLED"):
            return []

        opposite = "SELL" if taker.order_type == "BUY" else "BUY"
        statement = select(Order).where(
            Order.order_type == opposite,
            Order.status.in_(("OPEN", "PARTIALLY_FILLED")),
            Order.remaining_amount > 0,
            Order.creator_id != taker.creator_id,
        )

        if taker.order_type == "BUY":
            statement = statement.where(
                Order.price_per_token <= taker.price_per_token
            ).order_by(Order.price_per_token.asc(), Order.created_at.asc())
        else:
            statement = statement.where(
                Order.price_per_token >= taker.price_per_token
            ).order_by(Order.price_per_token.desc(), Order.created_at.asc())

        statement = statement.with_for_update(skip_locked=True)
        result = await session.exec(statement)
        makers = list(result.all())

        trades: list[Trade] = []
        for maker in makers:
            if taker.remaining_amount <= 0:
                break

            fill = min(taker.remaining_amount, maker.remaining_amount)
            if fill <= 0:
                continue

            buy_order = taker if taker.order_type == "BUY" else maker
            sell_order = taker if taker.order_type == "SELL" else maker
            buyer_id = buy_order.creator_id
            seller_id = sell_order.creator_id

            # The resting maker price is the execution price.
            execution_price = maker.price_per_token
            trade = Trade(
                idempotency_key=str(uuid.uuid4()),
                order_id=sell_order.id,
                buyer_id=buyer_id,
                seller_id=seller_id,
                token_amount=fill,
                execution_price=execution_price,
                status="PENDING",
            )
            session.add(trade)
            trades.append(trade)

            taker.remaining_amount -= fill
            maker.remaining_amount -= fill
            for order in (taker, maker):
                order.status = (
                    "FILLED" if order.remaining_amount == 0
                    else "PARTIALLY_FILLED"
                )

        return trades
