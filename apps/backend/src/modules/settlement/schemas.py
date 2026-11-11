"""API financial quantities are integer decimal strings, never JavaScript floats."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CalculateInterval(BaseModel):
    interval_start: datetime


class TransactionReference(BaseModel):
    transaction_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")
    action: Literal[
        "deposit",
        "withdraw",
        "withdraw_earnings",
        "escrow_sun",
        "withdraw_sun",
        "retire",
        "approve_sun",
        "approve_retirement",
        "cancel",
    ]


class BatchView(BaseModel):
    id: UUID
    community_id: UUID
    chain_batch_id: str
    interval_start: datetime
    interval_end: datetime
    status: str
    root: str
    injection_wh: int
    consumption_wh: int
    allocated_wh: int
    unallocated_wh: int
    uncompensated_wh: int
    total_due_wei: str
    policy_id: UUID


class AllocationView(BaseModel):
    id: UUID
    batch_id: UUID
    producer_id: UUID
    consumer_id: UUID
    chain_allocation_id: str
    energy_wh: int
    due_wei: str
    status: str
    funding_status: str
    proof: list[str]


class ClaimView(BaseModel):
    id: UUID
    batch_id: UUID
    kind: int
    chain_claim_id: str
    node_id: UUID
    meter_id: UUID
    chain_meter_id: str
    chain_node_id: str
    retirement_eligible: bool
    energy_wh: int
    status: str
    proof: list[str]


class ParticipantStatement(BaseModel):
    user_id: UUID
    asset: str
    available_wei: str
    reserved_wei: str
    claimable_wei: str
    settled_entitlement_wei: str
    withdrawn_earnings_wei: str
    unsettled_due_wei: str
    retired_wh: int
    block_number: int


class GovernancePrepare(BaseModel):
    salt: str = Field(
        default_factory=lambda: "0x" + uuid4().hex + uuid4().hex,
        pattern=r"^0x[0-9a-fA-F]{64}$",
    )
    action: Literal[
        "apply_membership",
        "transition",
        "membership",
        "node",
        "meter",
        "price",
        "finalize_batch",
    ]
    status: int = Field(default=0, ge=0, le=7)
    address: str = Field(default="0x" + "0" * 40, pattern=r"^0x[0-9a-fA-F]{40}$")
    node_id: UUID | None = None
    meter_id: UUID | None = None
    batch_id: UUID | None = None
    active: bool = True
    price_wei_per_kwh: str = Field(default="0", pattern=r"^\d+$", max_length=78)


class FundingView(BaseModel):
    allocation_id: UUID
    status: str
    due_wei: str
    available_wei: str | None
    reserved_wei: str | None
    available_sun_units: str | None
    required_sun_units: str
    confirmed_block: int
