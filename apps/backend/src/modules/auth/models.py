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
    from src.modules.home.models import Home
    from src.modules.wallet.models import Wallet


class User(SQLModel, table=True):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('user', 'admin', 'operator')",
            name="ck_users_role",
        ),
        Index("ix_users_email_lower", func.lower(text("email")), unique=True),
    )

    uid: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True, nullable=False),
    )

    username: str = Field(
        sa_column=Column(String(80), nullable=False),
    )

    email: str = Field(
        sa_column=Column(String(255), nullable=False),
    )

    first_name: str = Field(
        sa_column=Column(String(100), nullable=False),
    )

    last_name: str = Field(
        sa_column=Column(String(100), nullable=False),
    )

    role: str = Field(
        default="user",
        sa_column=Column(String(20), nullable=False, server_default="user"),
    )

    password_hash: str = Field(
        sa_column=Column(String(255), nullable=False),
        exclude=True,
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

    home: list["Home"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    wallets: list["Wallet"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"

