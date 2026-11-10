"""Community accounting uses the existing users, homes, meters and credits."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, Numeric, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


def now() -> datetime:
    return datetime.now(timezone.utc)


class EnergyCommunity(SQLModel, table=True):
    __tablename__ = "energy_communities"
    __table_args__ = (
        CheckConstraint(
            "sun_per_kwh > 0 AND loss_factor >= 0 AND loss_factor < 1",
            name="ck_community_policy",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PROPOSED','UNDER_REVIEW','APPROVED','ACTIVE','SUSPENDED','REJECTED','ARCHIVED') AND interval_seconds > 0",
            name="ck_community_lifecycle",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: str = Field(default="DRAFT", max_length=20)
    proposer_id: UUID | None = Field(default=None, foreign_key="users.uid")
    allow_simulated_telemetry: bool = False
    boundary_description: str = Field(default="", max_length=1000)
    topology: str = Field(default="SIMULATED_GRID_CONNECTED", max_length=50)
    policy_hash: str = Field(default="", max_length=66)
    boundary_hash: str = Field(default="", max_length=66)
    interval_seconds: int = Field(default=900)
    registry_address: str | None = Field(default=None, max_length=42)
    governance_transaction: str | None = Field(default=None, max_length=66)
    name: str = Field(max_length=150)
    sun_per_kwh: Decimal = Field(
        default=Decimal(1), sa_column=Column(Numeric(24, 8), nullable=False)
    )
    loss_factor: Decimal = Field(
        default=Decimal(0), sa_column=Column(Numeric(12, 8), nullable=False)
    )
    temporal_policy: str = Field(default="SAME_INTERVAL", max_length=30)
    created_at: datetime = Field(default_factory=now, sa_type=DateTime(timezone=True))


class CommunityMembership(SQLModel, table=True):
    __tablename__ = "community_memberships"
    __table_args__ = (
        UniqueConstraint("community_id", "user_id"),
        CheckConstraint(
            "role IN ('member','operator') AND status IN ('PENDING','APPROVED','ACTIVE','SUSPENDED','REVOKED')",
            name="ck_membership",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    user_id: UUID = Field(foreign_key="users.uid", index=True)
    role: str = Field(default="member", max_length=20)
    status: str = Field(default="ACTIVE", max_length=20)


class CommunityNode(SQLModel, table=True):
    __tablename__ = "community_nodes"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    home_id: UUID = Field(foreign_key="homes.id", unique=True)
    authorized: bool = False


class MeterAuthorization(SQLModel, table=True):
    __tablename__ = "meter_authorizations"
    device_id: UUID = Field(foreign_key="devices.id", primary_key=True)
    node_id: UUID = Field(foreign_key="community_nodes.id", index=True)
    credential_hash: str = Field(max_length=64)
    active: bool = True


class CommunityEnergyAllocation(SQLModel, table=True):
    __tablename__ = "community_energy_allocations"
    __table_args__ = (CheckConstraint("energy_wh > 0", name="ck_allocation_energy"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    injection_interval_id: UUID = Field(foreign_key="energy_intervals.id", index=True)
    withdrawal_interval_id: UUID = Field(foreign_key="energy_intervals.id", index=True)
    energy_wh: int
    created_at: datetime = Field(default_factory=now, sa_type=DateTime(timezone=True))


class CompensationRequest(SQLModel, table=True):
    __tablename__ = "compensation_requests"
    __table_args__ = (
        CheckConstraint(
            "energy_wh > 0 AND token_units > 0", name="ck_compensation_positive"
        ),
        CheckConstraint(
            "status IN ('RESERVED','AUTHORIZED','SUBMITTED','CONFIRMED','FAILED','RECONCILIATION')",
            name="ck_compensation_status",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    idempotency_key: str = Field(unique=True, max_length=128)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    user_id: UUID = Field(foreign_key="users.uid", index=True)
    allocation_id: UUID = Field(
        foreign_key="community_energy_allocations.id", unique=True
    )
    energy_wh: int
    token_units: Decimal = Field(sa_column=Column(Numeric(78, 0), nullable=False))
    wallet: str = Field(max_length=42)
    evidence_hash: str = Field(max_length=66)
    status: str = Field(default="RESERVED", max_length=20)
    transaction_hash: str | None = Field(default=None, unique=True, max_length=66)
    block_hash: str | None = Field(default=None, max_length=66)
    created_at: datetime = Field(default_factory=now, sa_type=DateTime(timezone=True))


class CommunityEnergyLedger(SQLModel, table=True):
    __tablename__ = "community_energy_ledger"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    operation: str = Field(max_length=40)
    source_id: UUID
    energy_wh: int = 0
    reference: str = Field(max_length=128, unique=True)
    blockchain_hash: str | None = Field(default=None, max_length=66)
    created_at: datetime = Field(default_factory=now, sa_type=DateTime(timezone=True))


class SettlementObligation(SQLModel, table=True):
    __tablename__ = "settlement_obligations"
    __table_args__ = (
        CheckConstraint(
            "sun_units > 0 AND payment_units > 0", name="ck_obligation_positive"
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    community_id: UUID = Field(foreign_key="energy_communities.id", index=True)
    order_id: int
    buyer: str = Field(max_length=42)
    seller: str = Field(max_length=42)
    sun_units: Decimal = Field(sa_column=Column(Numeric(78, 0), nullable=False))
    payment_units: Decimal = Field(sa_column=Column(Numeric(78, 0), nullable=False))
    payment_asset: str = Field(default="USDx_SIMULATED_PESO", max_length=40)
    transaction_hash: str = Field(max_length=66)
    log_index: int
    block_hash: str = Field(max_length=66)
    status: str = Field(default="CONFIRMED_SIMULATED", max_length=30)
    __table_args__ = (
        UniqueConstraint("transaction_hash", "log_index"),
        CheckConstraint(
            "sun_units > 0 AND payment_units > 0", name="ck_obligation_positive"
        ),
    )


class ChainDeployment(SQLModel, table=True):
    __tablename__ = "community_chain_deployments"
    community_id: UUID = Field(foreign_key="energy_communities.id", primary_key=True)
    chain_id: int
    sun_address: str = Field(max_length=42, unique=True)
    payment_address: str = Field(max_length=42)
    marketplace_address: str = Field(max_length=42, unique=True)
    compensation_address: str = Field(max_length=42, unique=True)


class ChainOperation(SQLModel, table=True):
    """Signed transaction persisted before broadcasting; retries use identical bytes."""

    __tablename__ = "community_chain_operations"
    __table_args__ = (UniqueConstraint("chain_id", "sender", "nonce"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    outbox_id: UUID = Field(foreign_key="outbox_events.id", unique=True)
    chain_id: int
    sender: str = Field(max_length=42)
    nonce: int
    transaction_hash: str = Field(max_length=66, unique=True)
    raw_transaction: str
    previous_transactions: list[dict] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    status: str = Field(default="PREPARED", max_length=20)
    block_hash: str | None = Field(default=None, max_length=66)


class ChainSyncState(SQLModel, table=True):
    """Confirmed log cursor per community; canonical hashes detect rewinds."""

    __tablename__ = "community_chain_sync_state"
    community_id: UUID = Field(foreign_key="energy_communities.id", primary_key=True)
    block_number: int = -1
    block_hash: str | None = Field(default=None, max_length=66)


class NativeDeployment(SQLModel, table=True):
    __tablename__ = "community_native_deployments"
    community_id: UUID = Field(foreign_key="energy_communities.id", primary_key=True)
    chain_id: int
    sun_address: str = Field(max_length=42)
    settlement_address: str = Field(max_length=42, unique=True)
    vault_address: str = Field(max_length=42, unique=True)
