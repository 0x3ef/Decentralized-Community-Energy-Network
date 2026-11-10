"""Marketplace API contracts."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderCreate(BaseModel):
    order_type: str = Field(pattern="^(BUY|SELL)$")
    token_amount: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    price_per_token: Decimal = Field(gt=0, max_digits=24, decimal_places=8)

    @model_validator(mode="after")
    def validate_values(self):
        if not self.token_amount.is_finite() or not self.price_per_token.is_finite():
            raise ValueError("Order values must be finite decimals")
        return self


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    creator_id: UUID
    order_type: str
    token_amount: Decimal
    price_per_token: Decimal
    remaining_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    buyer_id: UUID
    seller_id: UUID
    token_amount: Decimal
    execution_price: Decimal
    status: str
    created_at: datetime


class OrderBook(BaseModel):
    buy_orders: list[OrderRead]
    sell_orders: list[OrderRead]
