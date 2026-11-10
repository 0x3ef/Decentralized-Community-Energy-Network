from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.db import get_session
from src.modules.auth.dependencies import (
    RoleChecker
)
from .schemas import (
    HomeCreateModel,
    HomeModel,
    HomeUpdateModel
)
from .service import HomeService
from src.modules.auth.dependencies import get_current_user
from src.core.config import Config


home_router = APIRouter()
home_service = HomeService()
role_checker = RoleChecker(["admin", "user"])

@home_router.post("/", status_code=status.HTTP_201_CREATED)
async def create_home(home_data: HomeCreateModel, session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    user = await get_current_user()
    home = await home_service.create_home(user, home_data, session)

    return {"message": "Home created successfully", "home": home}

@home_router.get("/")
async def get_homes_by_user(user = Depends(get_current_user), session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    homes = await home_service.get_homes_by_user(user, session)

    if not homes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Homes not found for the user",
        )

    return {"homes": homes}

@home_router.get("/{home_id}")
async def get_home_by_id(home_id: str, user = Depends(get_current_user), session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    home = await home_service.get_home_by_id(user, home_id, session)

    if not home:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Home not found",
        )

    return {"home": home}

@home_router.patch("/{home_id}")
async def update_home(home_id: str, home_data: HomeUpdateModel, user = Depends(get_current_user), session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    updated_home = await home_service.update_home(user, home_id, home_data, session)

    return {"message": "Home updated successfully", "home": updated_home}


@home_router.delete("/{home_id}")
async def delete_home(home_id: str, user = Depends(get_current_user), session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    home = await home_service.get_home_by_id(user, home_id, session)

    if not home:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Home not found",
        )

    await home_service.delete_home(home, session)

    return {"message": "Home deleted successfully"}