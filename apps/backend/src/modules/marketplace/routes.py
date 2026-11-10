"""Marketplace HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from src.modules.marketplace.schemas import (
    OrderBook, OrderCreate, OrderRead, TradeRead,
)
from src.modules.marketplace.service import MarketplaceService
from src.modules.marketplace.settlement_service import SettlementService

marketplace_router = APIRouter()
service = MarketplaceService()
settlement_service = SettlementService()


@marketplace_router.get("/orderbook", response_model=OrderBook)
async def order_book(session: AsyncSession = Depends(get_session)):
    return await service.order_book(session)


@marketplace_router.post(
    "/orders", status_code=status.HTTP_201_CREATED
)
async def create_order(
    payload: OrderCreate,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        result = await service.create_order(user, payload, session)
        return {
            "order": OrderRead.model_validate(result["order"]),
            "trades": [TradeRead.model_validate(item) for item in result["trades"]],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@marketplace_router.get("/orders/me", response_model=list[OrderRead])
async def my_orders(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    return await service.my_orders(user, session)


@marketplace_router.delete("/orders/{order_id}", response_model=OrderRead)
async def cancel_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        return await service.cancel_order(user, order_id, session)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@marketplace_router.get("/trades/me", response_model=list[TradeRead])
async def my_trades(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    return await service.my_trades(user, session)


@marketplace_router.post("/trades/{trade_id}/settlement")
async def register_settlement(
    trade_id: UUID,
    tx_hash: str,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        record = await settlement_service.register_buyer_transaction(
            user, trade_id, tx_hash, session
        )
        return {
            "transaction_id": record.id,
            "transaction_hash": record.transaction_hash,
            "status": record.status,
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
