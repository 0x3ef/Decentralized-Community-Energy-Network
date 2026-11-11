"""Native protocol records; historical ERC20 obligations retain their own tables."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow():
    return datetime.now(UTC)


class SettlementPolicy(SQLModel, table=True):
    __tablename__ = "native_settlement_policies"
    __table_args__ = (
        UniqueConstraint("community_id", "policy_hash"),
        CheckConstraint(
            "price_wei_per_kwh > 0 AND interval_seconds > 0", name="ck_native_policy"
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    policy_hash: str = Field(max_length=66)
    price_wei_per_kwh: Decimal = Field(sa_column=Column(Numeric(78, 0), nullable=False))
    interval_seconds: int
    rules: dict = Field(sa_column=Column(JSONB, nullable=False))
    governance_reference: str = Field(max_length=66)
    created_at: datetime = Field(
        default_factory=utcnow, sa_type=DateTime(timezone=True)
    )


class SettlementBatch(SQLModel, table=True):
    __tablename__ = "native_settlement_batches"
    __table_args__ = (
        UniqueConstraint("community_id", "interval_start", "interval_end"),
        CheckConstraint(
            "interval_end > interval_start AND injection_wh >= allocated_wh AND consumption_wh >= allocated_wh AND allocated_wh >= 0",
            name="ck_native_batch_energy",
        ),
        CheckConstraint(
            "status IN ('PREPARED','SUBMITTED','CHALLENGEABLE','FINALIZED','REJECTED','SUPERSEDED','RECONCILIATION_REQUIRED')",
            name="ck_native_batch_status",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    policy_id: UUID = Field(foreign_key="native_settlement_policies.id")
    interval_start: datetime = Field(sa_type=DateTime(timezone=True))
    interval_end: datetime = Field(sa_type=DateTime(timezone=True))
    chain_batch_id: str = Field(unique=True, max_length=66)
    root: str = Field(max_length=66)
    injection_wh: int = Field(sa_type=BigInteger)
    consumption_wh: int = Field(sa_type=BigInteger)
    allocated_wh: int = Field(sa_type=BigInteger)
    total_due_wei: Decimal = Field(sa_column=Column(Numeric(78, 0), nullable=False))
    evidence: dict = Field(sa_column=Column(JSONB, nullable=False))
    status: str = Field(default="PREPARED", max_length=30, index=True)
    created_at: datetime = Field(
        default_factory=utcnow, sa_type=DateTime(timezone=True)
    )


class SettlementClaim(SQLModel, table=True):
    __tablename__ = "native_settlement_claims"
    __table_args__ = (
        UniqueConstraint("batch_id", "kind", "node_id"),
        CheckConstraint("energy_wh > 0 AND kind IN (0,1)", name="ck_native_claim"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    batch_id: UUID = Field(foreign_key="native_settlement_batches.id", index=True)
    user_id: UUID = Field(foreign_key="users.uid", index=True)
    node_id: UUID = Field(foreign_key="community_nodes.id")
    meter_id: UUID = Field(foreign_key="devices.id")
    interval_id: UUID = Field(foreign_key="energy_intervals.id")
    energy_credit_id: UUID | None = Field(
        default=None, foreign_key="energy_credits.id", unique=True
    )
    kind: int
    chain_claim_id: str = Field(unique=True, max_length=66)
    wallet: str = Field(max_length=42)
    energy_wh: int = Field(sa_type=BigInteger)
    proof: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    status: str = Field(default="ELIGIBLE", max_length=30)


class IntervalAllocation(SQLModel, table=True):
    __tablename__ = "native_interval_allocations"
    __table_args__ = (
        UniqueConstraint("batch_id", "producer_node_id", "consumer_node_id"),
        CheckConstraint(
            "energy_wh > 0 AND due_wei > 0 AND consumer_cap_wh >= energy_wh",
            name="ck_native_allocation",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    batch_id: UUID = Field(foreign_key="native_settlement_batches.id", index=True)
    producer_id: UUID = Field(foreign_key="users.uid", index=True)
    consumer_id: UUID = Field(foreign_key="users.uid", index=True)
    producer_node_id: UUID = Field(foreign_key="community_nodes.id")
    consumer_node_id: UUID = Field(foreign_key="community_nodes.id")
    injection_interval_id: UUID = Field(foreign_key="energy_intervals.id")
    consumption_interval_id: UUID = Field(foreign_key="energy_intervals.id")
    producer_wallet: str = Field(max_length=42)
    consumer_wallet: str = Field(max_length=42)
    chain_allocation_id: str = Field(unique=True, max_length=66)
    energy_wh: int = Field(sa_type=BigInteger)
    consumer_cap_wh: int = Field(sa_type=BigInteger)
    due_wei: Decimal = Field(sa_column=Column(Numeric(78, 0), nullable=False))
    proof: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    funding_status: str = Field(default="UNFUNDED", max_length=30)
    status: str = Field(default="ELIGIBLE", max_length=30, index=True)


class IndexedNativeEvent(SQLModel, table=True):
    __tablename__ = "native_indexed_events"
    __table_args__ = (
        UniqueConstraint("chain_id", "transaction_hash", "log_index", "block_hash"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    chain_id: int
    address: str = Field(max_length=42)
    transaction_hash: str = Field(max_length=66, index=True)
    log_index: int
    block_number: int = Field(sa_type=BigInteger)
    block_hash: str = Field(max_length=66)
    event_name: str = Field(max_length=60)
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))
    canonical: bool = True


class NativeWalletTransaction(SQLModel, table=True):
    __tablename__ = "native_wallet_transactions"
    __table_args__ = (UniqueConstraint("chain_id", "transaction_hash"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    user_id: UUID = Field(foreign_key="users.uid", index=True)
    chain_id: int
    transaction_hash: str = Field(max_length=66)
    action: str = Field(max_length=40)
    status: str = Field(default="SUBMITTED", max_length=30)
    block_hash: str | None = Field(default=None, max_length=66)
    created_at: datetime = Field(
        default_factory=utcnow, sa_type=DateTime(timezone=True)
    )


class NativeSyncCursor(SQLModel, table=True):
    __tablename__ = "native_sync_cursors"
    community_id: UUID = Field(foreign_key="energy_communities.id", primary_key=True)
    block_number: int = Field(default=-1, sa_type=BigInteger)
    block_hash: str | None = Field(default=None, max_length=66)
