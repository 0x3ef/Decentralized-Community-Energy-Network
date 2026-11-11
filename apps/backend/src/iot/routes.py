"""Authenticated telemetry quality and readiness reads; no credential exposure."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.db import get_session
from src.iot.service import TelemetryHealthService
from src.modules.auth.dependencies import get_current_user

router = APIRouter()
User = Annotated[Any, Depends(get_current_user)]
Session = Annotated[Any, Depends(get_session)]


@router.get("/devices/{device_id}/health")
async def health(device_id: UUID, user: User, session: Session):
    return await TelemetryHealthService().health(session, user, device_id)


@router.get("/devices/{device_id}/quality")
async def quality(
    device_id: UUID,
    user: User,
    session: Session,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await TelemetryHealthService().evidence(
        session, user, device_id, limit, offset
    )
