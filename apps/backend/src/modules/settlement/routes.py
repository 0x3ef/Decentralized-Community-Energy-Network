"""Thin authenticated native protocol routes; no service custody of user ETH."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from src.modules.community.models import (
    ChainOperation,
)
from src.modules.community.service import CommunityService
from src.modules.device.models import Device
from src.modules.energy.models import OutboxEvent
from src.modules.settlement.chain import NativeSettlementChain, binary
from src.modules.settlement.engine import key
from src.modules.settlement.models import (
    IndexedNativeEvent,
    IntervalAllocation,
    NativeWalletTransaction,
    SettlementBatch,
    SettlementClaim,
)
from src.modules.settlement.schemas import (
    AllocationView,
    BatchView,
    CalculateInterval,
    ClaimView,
    FundingView,
    GovernancePrepare,
    ParticipantStatement,
    TransactionReference,
)
from src.modules.settlement.support import GovernanceService, NativeTransactionService
from web3 import Web3

router = APIRouter()
User = Annotated[Any, Depends(get_current_user)]
Session = Annotated[Any, Depends(get_session)]


def batch_view(row):
    return BatchView(
        **{
            **row.model_dump(),
            "total_due_wei": str(int(row.total_due_wei)),
            "unallocated_wh": row.injection_wh - row.allocated_wh,
            "uncompensated_wh": row.consumption_wh - row.allocated_wh,
        }
    )


def allocation_view(row):
    return AllocationView(**{**row.model_dump(), "due_wei": str(int(row.due_wei))})


async def access(session, community_id, user, operator=False):
    return await CommunityService().membership(
        session, community_id, user.uid, operator=operator
    )


@router.post("/{community_id}/settlements/calculate", response_model=BatchView)
async def calculate(
    community_id: UUID, payload: CalculateInterval, user: User, session: Session
):
    await access(session, community_id, user, True)
    row = await NativeSettlementChain().service.calculate_interval(
        session, community_id, payload.interval_start
    )
    await session.commit()
    return batch_view(row)


@router.get("/{community_id}/settlements", response_model=list[BatchView])
async def history(
    community_id: UUID,
    user: User,
    session: Session,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await access(session, community_id, user)
    query = select(SettlementBatch).where(SettlementBatch.community_id == community_id)
    if status:
        query = query.where(SettlementBatch.status == status)
    rows = (
        await session.exec(
            query.order_by(SettlementBatch.interval_start.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [batch_view(r) for r in rows]


async def batch_access(session, community_id, batch_id, user):
    await access(session, community_id, user)
    batch = await session.get(SettlementBatch, batch_id)
    if not batch or batch.community_id != community_id:
        raise LookupError("Community interval settlement not found")
    return batch


@router.get("/{community_id}/settlements/{batch_id}", response_model=BatchView)
async def details(community_id: UUID, batch_id: UUID, user: User, session: Session):
    return batch_view(await batch_access(session, community_id, batch_id, user))


@router.get(
    "/{community_id}/settlements/{batch_id}/allocations",
    response_model=list[AllocationView],
)
async def allocations(
    community_id: UUID,
    batch_id: UUID,
    user: User,
    session: Session,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await batch_access(session, community_id, batch_id, user)
    rows = (
        await session.exec(
            select(IntervalAllocation)
            .where(
                IntervalAllocation.batch_id == batch_id,
                (IntervalAllocation.producer_id == user.uid)
                | (IntervalAllocation.consumer_id == user.uid),
            )
            .order_by(IntervalAllocation.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [allocation_view(r) for r in rows]


@router.get(
    "/{community_id}/settlements/{batch_id}/claims", response_model=list[ClaimView]
)
async def claims(
    community_id: UUID,
    batch_id: UUID,
    user: User,
    session: Session,
    kind: int | None = Query(None, ge=0, le=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await batch_access(session, community_id, batch_id, user)
    query = select(SettlementClaim).where(
        SettlementClaim.batch_id == batch_id, SettlementClaim.user_id == user.uid
    )
    if kind is not None:
        query = query.where(SettlementClaim.kind == kind)
    rows = (
        await session.exec(
            query.order_by(SettlementClaim.id).offset(offset).limit(limit)
        )
    ).all()
    chain = NativeSettlementChain()
    _, _, _, _, vault = await chain.service.contracts(session, community_id)
    height = chain.confirmed_height()
    batch = await session.get(SettlementBatch, batch_id)
    result = []
    for row in rows:
        device = await session.get(Device, row.meter_id)
        delivered = (
            vault.functions.deliveredEnergyByNode(
                binary(batch.chain_batch_id), key(row.node_id)
            ).call(block_identifier=height)
            if row.kind == 1
            else 0
        )
        result.append(
            ClaimView(
                **row.model_dump(),
                chain_meter_id=Web3.to_hex(key(device.device_id)),
                chain_node_id=Web3.to_hex(key(row.node_id)),
                retirement_eligible=row.kind == 1
                and delivered >= row.energy_wh
                and row.status != "RETIRED",
            )
        )
    return result


@router.get("/{community_id}/settlement-statement", response_model=ParticipantStatement)
async def statement(community_id: UUID, user: User, session: Session):
    await access(session, community_id, user)
    chain = NativeSettlementChain()
    _, deployment, _, _, vault = await chain.service.contracts(session, community_id)
    wallet = await CommunityService().wallet(session, user.uid)
    height = chain.confirmed_height()
    allocations = (
        await session.exec(
            select(IntervalAllocation)
            .join(SettlementBatch, SettlementBatch.id == IntervalAllocation.batch_id)
            .where(
                SettlementBatch.community_id == community_id,
                (IntervalAllocation.producer_id == user.uid)
                | (IntervalAllocation.consumer_id == user.uid),
            )
        )
    ).all()
    retirements = (
        await session.exec(
            select(SettlementClaim)
            .join(SettlementBatch, SettlementBatch.id == SettlementClaim.batch_id)
            .where(
                SettlementBatch.community_id == community_id,
                SettlementClaim.user_id == user.uid,
                SettlementClaim.kind == 1,
                SettlementClaim.status == "RETIRED",
            )
        )
    ).all()
    withdrawals = (
        await session.exec(
            select(IndexedNativeEvent).where(
                IndexedNativeEvent.community_id == community_id,
                IndexedNativeEvent.canonical.is_(True),
                IndexedNativeEvent.event_name == "Withdrawn",
            )
        )
    ).all()
    return ParticipantStatement(
        user_id=user.uid,
        asset="Sepolia ETH" if deployment.chain_id == 11155111 else "Anvil ETH",
        available_wei=str(
            vault.functions.available(wallet).call(block_identifier=height)
        ),
        reserved_wei=str(
            vault.functions.reserved(wallet).call(block_identifier=height)
        ),
        claimable_wei=str(
            vault.functions.earnings(wallet).call(block_identifier=height)
        ),
        withdrawn_earnings_wei=str(
            sum(
                int(e.payload["amount"])
                for e in withdrawals
                if e.payload.get("producerEarnings")
                and e.payload.get("member", "").lower() == wallet.lower()
            )
        ),
        settled_entitlement_wei=str(
            sum(
                int(r.due_wei)
                for r in allocations
                if r.status == "SETTLED" and r.producer_id == user.uid
            )
        ),
        unsettled_due_wei=str(
            sum(
                int(r.due_wei)
                for r in allocations
                if r.status not in ("SETTLED", "CANCELLED")
                and r.consumer_id == user.uid
            )
        ),
        retired_wh=sum(r.energy_wh for r in retirements),
        block_number=height,
    )


@router.get("/{community_id}/settlements/{batch_id}/operations")
async def operations(
    community_id: UUID,
    batch_id: UUID,
    user: User,
    session: Session,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await batch_access(session, community_id, batch_id, user)
    # Oracle job metadata is operator-only; raw signed bytes are never exposed.
    await access(session, community_id, user, True)
    rows = (
        await session.exec(
            select(OutboxEvent, ChainOperation)
            .outerjoin(ChainOperation, ChainOperation.outbox_id == OutboxEvent.id)
            .where(
                OutboxEvent.event_type.like("native.%"),
                OutboxEvent.payload["batch_id"].astext == str(batch_id),
            )
            .order_by(OutboxEvent.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            "job_id": j.id,
            "action": j.event_type,
            "status": j.status,
            "attempts": j.attempts,
            "last_error": j.last_error,
            "transaction_hash": o.transaction_hash if o else None,
            "chain_status": o.status if o else None,
            "operation_id": o.id if o else None,
        }
        for j, o in rows
    ]


@router.post(
    "/{community_id}/settlements/{batch_id}/reconcile", response_model=BatchView
)
async def reconcile(community_id: UUID, batch_id: UUID, user: User, session: Session):
    await batch_access(session, community_id, batch_id, user)
    await access(session, community_id, user, True)
    chain = NativeSettlementChain()
    await chain.service.repository.lock(session, f"native-reconcile:{community_id}")
    await chain.audit_native(session, community_id)
    await chain.index_native(session, community_id)
    await session.commit()
    return batch_view(await session.get(SettlementBatch, batch_id))


@router.post("/{community_id}/native/transactions", status_code=202)
async def track_transaction(
    community_id: UUID, payload: TransactionReference, user: User, session: Session
):
    # Track exits even after suspension. Chain receipt validation never invents balances.
    return await NativeTransactionService().track(community_id, payload, user, session)


@router.get("/{community_id}/native/transactions")
async def wallet_transactions(
    community_id: UUID,
    user: User,
    session: Session,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return (
        await session.exec(
            select(NativeWalletTransaction)
            .where(
                NativeWalletTransaction.community_id == community_id,
                NativeWalletTransaction.user_id == user.uid,
            )
            .order_by(NativeWalletTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()


@router.post("/{community_id}/governance/prepare")
async def governance_prepare(
    community_id: UUID, payload: GovernancePrepare, user: User, session: Session
):
    return await GovernanceService().prepare(community_id, payload, user, session)


@router.post("/{community_id}/memberships/apply", status_code=201)
async def apply_membership(community_id: UUID, user: User, session: Session):
    return await GovernanceService().apply(community_id, user, session)


@router.post("/{community_id}/memberships/sync")
async def sync_membership(community_id: UUID, user: User, session: Session):
    return await GovernanceService().sync(community_id, user, session)


@router.post(
    "/{community_id}/settlements/{batch_id}/jobs/{job_id}/retry", status_code=202
)
async def retry_job(
    community_id: UUID, batch_id: UUID, job_id: UUID, user: User, session: Session
):
    await batch_access(session, community_id, batch_id, user)
    await access(session, community_id, user, True)
    job = (
        await session.exec(
            select(OutboxEvent).where(OutboxEvent.id == job_id).with_for_update()
        )
    ).first()
    if (
        not job
        or job.payload.get("batch_id") != str(batch_id)
        or not job.event_type.startswith("native.")
    ):
        raise LookupError("Native batch job not found")
    if job.status != "FAILED":
        raise ValueError("Only a terminal failed job may be explicitly retried")
    job.status = "RETRIED"
    retry = OutboxEvent(
        event_type=job.event_type,
        aggregate_type=job.aggregate_type,
        aggregate_id=job.aggregate_id,
        payload={**job.payload, "retry_of": str(job.id)},
    )
    session.add(retry)
    await session.commit()
    return {"job_id": retry.id, "status": retry.status}


@router.get(
    "/{community_id}/allocations/{allocation_id}/funding", response_model=FundingView
)
async def funding(
    community_id: UUID, allocation_id: UUID, user: User, session: Session
):
    await access(session, community_id, user)
    row = await session.get(IntervalAllocation, allocation_id)
    if not row or user.uid not in (row.producer_id, row.consumer_id):
        raise LookupError("Participant allocation not found")
    batch = await session.get(SettlementBatch, row.batch_id)
    if batch.community_id != community_id:
        raise LookupError("Participant allocation not found")
    chain = NativeSettlementChain()
    _, _, _, _, vault = await chain.service.contracts(session, community_id)
    height = chain.confirmed_height()
    view = FundingView(
        allocation_id=row.id,
        status=await chain.service.verify_funding(session, row, height),
        due_wei=str(int(row.due_wei)),
        available_wei=str(
            vault.functions.available(row.consumer_wallet).call(block_identifier=height)
        ),
        reserved_wei=str(
            vault.functions.reserved(row.consumer_wallet).call(block_identifier=height)
        ),
        available_sun_units=str(
            vault.functions.sunAvailable(row.producer_wallet).call(
                block_identifier=height
            )
        ),
        required_sun_units=str(row.energy_wh * 10**15),
        confirmed_block=height,
    )

    if row.consumer_id != user.uid:
        view.available_wei = None
        view.reserved_wei = None
    if row.producer_id != user.uid:
        view.available_sun_units = None
    return view


@router.get("/{community_id}/settlement-policy")
async def policy(community_id: UUID, user: User, session: Session):
    await access(session, community_id, user)
    chain = NativeSettlementChain()
    row = await chain.service.policy(session, community_id)
    await session.commit()
    return {**row.model_dump(), "price_wei_per_kwh": str(int(row.price_wei_per_kwh))}
