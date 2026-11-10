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

# ============================================================
# ENERGY INTERVALS
# ============================================================

class EnergyInterval(SQLModel, table=True):
    __tablename__ = "energy_intervals"

    __table_args__ = (
        UniqueConstraint(
            "home_id",
            "interval_start",
            "interval_end",
            name="uq_energy_home_interval",
        ),
        CheckConstraint(
            "interval_end > interval_start",
            name="ck_energy_interval_order",
        ),
        CheckConstraint(
            """
            generation_wh >= 0
            AND consumption_wh >= 0
            AND grid_import_wh >= 0
            AND grid_export_wh >= 0
            AND battery_charge_wh >= 0
            AND battery_discharge_wh >= 0
            AND eligible_export_wh >= 0
            """,
            name="ck_energy_nonnegative",
        ),
        Index(
            "ix_energy_home_start",
            "home_id",
            "interval_start",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    home_id: uuid.UUID = Field(
        foreign_key="homes.id",
        nullable=False,
        index=True,
    )

    interval_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    interval_end: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    generation_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    consumption_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    grid_import_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    grid_export_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    battery_charge_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    battery_discharge_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    eligible_export_wh: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )

    calculation_version: str = Field(
        default="v1",
        sa_column=Column(String(30), nullable=False),
    )

    quality_status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    home: Optional["Home"] = Relationship(
        back_populates="intervals",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    credits: list["EnergyCredit"] = Relationship(
        back_populates="interval",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


# ============================================================
# ENERGY CREDITS
# ============================================================

class EnergyCredit(SQLModel, table=True):
    __tablename__ = "energy_credits"

    __table_args__ = (
        UniqueConstraint(
            "interval_id",
            "owner_id",
            name="uq_energy_credit_interval_owner",
        ),
        CheckConstraint(
            "energy_wh > 0",
            name="ck_credit_energy_positive",
        ),
        CheckConstraint(
            "token_amount > 0",
            name="ck_credit_token_positive",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'ISSUANCE_PENDING', "
            "'ISSUED', 'REJECTED', 'FAILED')",
            name="ck_credit_status",
        ),
        Index("ix_credit_owner_status", "owner_id", "status"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    interval_id: uuid.UUID = Field(
        foreign_key="energy_intervals.id",
        nullable=False,
        index=True,
    )

    owner_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
        index=True,
    )

    energy_wh: int = Field(
        sa_column=Column(BigInteger, nullable=False),
    )

    token_amount: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False),
    )

    status: str = Field(
        default="PENDING",
        sa_column=Column(
            String(30),
            nullable=False,
            server_default="PENDING",
        ),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )

    interval: Optional["EnergyInterval"] = Relationship(
        back_populates="credits",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

# ============================================================
# CREDIT MOVEMENTS
# ============================================================

class CreditMovement(SQLModel, table=True):
    __tablename__ = "credit_movements"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_credit_movement_amount_positive",
        ),
        Index(
            "ix_credit_movement_owner_created",
            "owner_id",
            "created_at",
        ),
        Index(
            "ix_credit_movement_credit",
            "credit_id",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    credit_id: uuid.UUID = Field(
        foreign_key="energy_credits.id",
        nullable=False,
        index=True,
    )

    owner_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
        index=True,
    )

    counterparty_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="users.uid",
    )

    movement_type: str = Field(
        sa_column=Column(String(20), nullable=False)
    )

    amount: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    reference_type: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50)),
    )

    reference_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(pg.UUID),
    )

    idempotency_key: str = Field(
        sa_column=Column(
            String(128),
            nullable=False,
            unique=True,
        )
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


# ============================================================
# BLOCKCHAIN TRANSACTIONS
# ============================================================

class BlockchainTransaction(SQLModel, table=True):
    __tablename__ = "blockchain_transactions"

    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "transaction_hash",
            name="uq_blockchain_chain_tx_hash",
        ),
        Index("ix_blockchain_status", "status"),
        Index("ix_blockchain_entity", "entity_type", "entity_id"),
        Index("ix_blockchain_sender_nonce", "sender", "nonce"),
        CheckConstraint("chain_id > 0", name="ck_blockchain_chain_positive"),
        CheckConstraint("retry_count >= 0", name="ck_blockchain_retry_nonnegative"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    idempotency_key: str = Field(
        sa_column=Column(String(128), nullable=False, unique=True),
    )

    chain_id: int = Field(
        sa_column=Column(BigInteger, nullable=False),
    )

    contract_address: str = Field(
        sa_column=Column(String(42), nullable=False),
    )

    transaction_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(66)),
    )

    sender: Optional[str] = Field(
        default=None,
        sa_column=Column(String(42)),
    )

    recipient: Optional[str] = Field(
        default=None,
        sa_column=Column(String(42)),
    )

    operation_type: str = Field(
        sa_column=Column(String(50), nullable=False),
    )

    entity_type: str = Field(
        sa_column=Column(String(50), nullable=False),
    )

    entity_id: uuid.UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), nullable=False),
    )

    nonce: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False, server_default="PENDING"),
    )

    block_number: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    block_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(66)),
    )

    gas_used: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    gas_price_wei: Optional[int] = Field(
        default=None,
        sa_column=Column(Numeric(30, 0)),
    )

    failure_reason: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    retry_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )

    submitted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    confirmed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    events: list["BlockchainEvent"] = Relationship(
        back_populates="transaction",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

# ============================================================
# BLOCKCHAIN EVENTS
# ============================================================

class BlockchainEvent(SQLModel, table=True):
    __tablename__ = "blockchain_events"

    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "contract_address",
            "block_number",
            "log_index",
            name="uq_chain_log",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    transaction_id: uuid.UUID = Field(
        foreign_key="blockchain_transactions.id",
        nullable=False,
        index=True,
    )

    chain_id: int = Field(
        sa_column=Column(BigInteger, nullable=False)
    )

    contract_address: str = Field(
        sa_column=Column(String(42), nullable=False)
    )

    event_name: str = Field(
        sa_column=Column(String(100), nullable=False)
    )

    block_number: int = Field(
        sa_column=Column(BigInteger, nullable=False)
    )

    log_index: int = Field(
        sa_column=Column(BigInteger, nullable=False)
    )

    payload: dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False)
    )

    transaction: Optional["BlockchainTransaction"] = Relationship(
        back_populates="events",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


# ============================================================
# OUTBOX EVENTS
# ============================================================

class OutboxEvent(SQLModel, table=True):
    __tablename__ = "outbox_events"

    __table_args__ = (
        Index(
            "ix_outbox_pending",
            "available_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_outbox_processing",
            "locked_at",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
        Index(
            "ix_outbox_aggregate",
            "aggregate_type",
            "aggregate_id",
        ),
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    event_type: str = Field(
        sa_column=Column(String(100), nullable=False),
    )

    aggregate_type: str = Field(
        sa_column=Column(String(50), nullable=False),
    )

    aggregate_id: uuid.UUID = Field(
        sa_column=Column(pg.UUID(as_uuid=True), nullable=False),
    )

    payload: dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False),
    )

    status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False, server_default="PENDING"),
    )

    attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )

    available_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    locked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    locked_by: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    processed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    last_error: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

# ============================================================
# MARKETPLACE ORDERS
# ============================================================

class Order(SQLModel, table=True):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint(
            "token_amount > 0 "
            "AND remaining_amount >= 0 "
            "AND remaining_amount <= token_amount",
            name="ck_order_amounts",
        ),
        CheckConstraint(
            "price_per_token >= 0",
            name="ck_order_price_nonnegative",
        ),
        CheckConstraint(
            "order_type IN ('BUY', 'SELL')",
            name="ck_order_type",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED')",
            name="ck_order_status",
        ),
        Index(
            "ix_orders_status_type",
            "status",
            "order_type",
        ),
        Index(
            "ix_orders_creator_status",
            "creator_id",
            "status",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    creator_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
        index=True,
    )

    order_type: str = Field(
        sa_column=Column(String(10), nullable=False)
    )

    token_amount: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    price_per_token: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    remaining_amount: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    status: str = Field(
        default="OPEN",
        sa_column=Column(String(20), nullable=False),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


# ============================================================
# TRADES
# ============================================================

class Trade(SQLModel, table=True):
    __tablename__ = "trades"

    __table_args__ = (
        CheckConstraint(
            "token_amount > 0",
            name="ck_trade_amount_positive",
        ),
        CheckConstraint(
            "execution_price >= 0",
            name="ck_trade_price_nonnegative",
        ),
        Index(
            "ix_trades_buyer",
            "buyer_id",
        ),
        Index(
            "ix_trades_seller",
            "seller_id",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    idempotency_key: str = Field(
        sa_column=Column(String(128), nullable=False, unique=True),
    )

    order_id: uuid.UUID = Field(
        foreign_key="orders.id",
        nullable=False,
        index=True,
    )

    buyer_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
    )

    seller_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
    )

    token_amount: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    execution_price: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


# ============================================================
# REDEMPTIONS
# ============================================================

class Redemption(SQLModel, table=True):
    __tablename__ = "redemptions"

    __table_args__ = (
        CheckConstraint(
            "token_amount > 0",
            name="ck_redemption_amount_positive",
        ),
        CheckConstraint(
            "compensation_amount >= 0",
            name="ck_redemption_compensation_nonnegative",
        ),
        Index(
            "ix_redemption_user_status",
            "user_id",
            "status",
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

    wallet_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="wallets.id",
    )

    token_amount: Decimal = Field(
        sa_column=Column(Numeric(24, 8), nullable=False)
    )

    compensation_amount: Decimal = Field(
        sa_column=Column(Numeric(18, 2), nullable=False)
    )

    currency: str = Field(
        default="COP",
        sa_column=Column(String(10), nullable=False),
    )

    status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False),
    )

    external_reference: Optional[str] = Field(
        default=None,
        sa_column=Column(String(128), unique=True),
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


# ============================================================
# AUDIT EVENTS
# ============================================================

class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"

    __table_args__ = (
        Index(
            "ix_audit_actor_created",
            "actor_id",
            "created_at",
        ),
        Index(
            "ix_audit_entity",
            "entity_type",
            "entity_id",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    actor_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="users.uid",
    )

    actor_type: str = Field(
        default="USER",
        sa_column=Column(String(30), nullable=False),
    )

    event_type: str = Field(
        sa_column=Column(String(100), nullable=False)
    )

    entity_type: str = Field(
        sa_column=Column(String(100), nullable=False)
    )

    entity_id: uuid.UUID = Field(
        sa_column=Column(pg.UUID, nullable=False)
    )

    metadata_json: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column("metadata", JSONB),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class EnergyPowerSnapshot(SQLModel, table=True):
    """Previous battery power sample for explicit trapezoidal integration."""
    __tablename__ = "energy_power_snapshots"
    __table_args__ = (CheckConstraint("power_w >= 0", name="ck_energy_power_nonnegative"),)
    device_id: uuid.UUID = Field(foreign_key="devices.id", primary_key=True)
    channel: str = Field(max_length=30, primary_key=True)
    power_w: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False))
    measured_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
