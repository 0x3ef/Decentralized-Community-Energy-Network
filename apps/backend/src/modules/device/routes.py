from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.db import get_session


from .schemas import (
    DeviceCreateModel,
    DeviceModel,
    DeviceUpdateModel,
    DeviceCredentialIssue
)

from .service import DeviceService
from src.modules.auth.dependencies import get_current_user
from src.core.config import Config


device_router = APIRouter()
device_service = DeviceService()

@device_router.post("/device", status_code=status.HTTP_201_CREATED)
async def create_device(device_data: DeviceCreateModel, session: AsyncSession = Depends(get_session)):
    user = await get_current_user()
    device = await device_service.create_device(user, device_data, session)

    return {"message": "Device created successfully", "device": device}

@device_router.get("/device/")
async def get_devices_by_home(home_id: str, session: AsyncSession = Depends(get_session)):
    user = await get_current_user()
    devices = await device_service.get_devices_by_home(user, home_id, session)

    if not devices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Devices not found for the home",
        )

    return {"devices": devices}

@device_router.get("/device/{device_id}")
async def get_device_by_id(device_id: str, session: AsyncSession = Depends(get_session)):
    device = await device_service.get_device_by_id(device_id, session)

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    return {"device": device}

@device_router.patch("/device/{device_id}")
async def update_device(device_id: str, device_data: DeviceUpdateModel, session: AsyncSession = Depends(get_session)):
    user = await get_current_user()
    updated_device = await device_service.update_device(user, device_id, device_data, session)

    if not updated_device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    return {"message": "Device updated successfully", "device": updated_device}


@device_router.delete("/device/{device_id}")
async def delete_device(device_id: str, session: AsyncSession = Depends(get_session)):
    user = await get_current_user()
    device = await device_service.get_device_by_id(device_id, session)

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    await device_service.delete_device(user, device_id, session)

    return {"message": "Device deleted successfully"}