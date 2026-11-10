"""HTTP endpoints for energy intervals, summaries and credits."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from src.modules.energy.schemas import (
    CreditApprovalResult, EnergyCreditReadModel,
    EnergyIntervalReadModel, EnergySummaryModel,
)
from src.modules.energy.service import EnergyService

energy_router = APIRouter()
energy_service = EnergyService()


@energy_router.get(
    "/homes/{home_id}/energy/intervals",
    response_model=list[EnergyIntervalReadModel],
)
async def list_energy_intervals(
    home_id: UUID,
    start: datetime,
    end: datetime,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        return await energy_service.list_intervals(
            user, home_id, start, end, session
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@energy_router.get(
    "/homes/{home_id}/energy/summary",
    response_model=EnergySummaryModel,
)
async def energy_summary(
    home_id: UUID,
    start: datetime,
    end: datetime,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        return await energy_service.summary(user, home_id, start, end, session)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@energy_router.get("/credits", response_model=list[EnergyCreditReadModel])
async def list_my_credits(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    return await energy_service.credits(user, session)


@energy_router.get(
    "/credits/{credit_id}", response_model=EnergyCreditReadModel
)
async def get_credit(
    credit_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        credit = await energy_service.credit(user, credit_id, session)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if credit is None:
        raise HTTPException(status_code=404, detail="Credit not found")
    return credit


@energy_router.post(
    "/credits/{credit_id}/approve",
    response_model=CreditApprovalResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_credit(
    credit_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    try:
        credit = await energy_service.approve_credit(user, credit_id, session)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CreditApprovalResult(
        id=credit.id,
        status=credit.status,
        message="Credit approved and queued for blockchain issuance",
    )
