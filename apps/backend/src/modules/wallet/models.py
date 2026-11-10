import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.modules.auth.models import User


class Wallet(SQLModel, table=True):
    __tablename__ = "wallets"

    __table_args__ = (
        UniqueConstraint("address", name="uq_wallets_address"),
        UniqueConstraint("user_id", "address", name="uq_wallet_user_address"),
        CheckConstraint(
            "address ~ '^0x[a-fA-F0-9]{40}$'",
            name="ck_wallet_address_format",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    user_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
        index=True,
    )

    address: str = Field(
        sa_column=Column(String(42), nullable=False),
    )

    is_verified: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    user: Optional["User"] = Relationship(
        back_populates="wallets",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class WalletNonce(SQLModel, table=True):
    __tablename__ = "wallet_nonces"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    user_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
        index=True,
    )

    address: str = Field(
        sa_column=Column(
            String(42),
            nullable=False,
            index=True,
        )
    )

    nonce: str = Field(
        sa_column=Column(
            String(128),
            unique=True,
            nullable=False,
        )
    )

    expires_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
        )
    )

    used_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )
