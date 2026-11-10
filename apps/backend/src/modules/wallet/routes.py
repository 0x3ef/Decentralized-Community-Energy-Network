from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.db import get_session


from .schemas import (
    WalletCreateModel,
    WalletModel
)
from .service import WalletService
from src.modules.auth.dependencies import (
    RoleChecker,
    get_current_user
)
from src.core.config import Config


wallet_router = APIRouter()
wallet_service = WalletService()
role_checker = RoleChecker(["admin", "user"])

@wallet_router.post("/", status_code=status.HTTP_201_CREATED)
async def create_wallet(wallet_data: WalletCreateModel, session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    wallet = await wallet_service.create_wallet(wallet_data, session)

    return {"message": "Wallet created successfully", "wallet": wallet}



@wallet_router.get("/{user_id}")
async def get_wallets_by_user(user_id: str, session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    wallets = await wallet_service.get_wallets_by_user(user_id, session)

    if not wallets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallets not found for the user",
        )

    return {"wallets": wallets}
    

@wallet_router.get("/{address}")
async def get_wallet_by_address(address: str, session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    wallet = await wallet_service.get_wallet_by_address(address, session)

    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    return {"wallet": wallet}


@wallet_router.delete("/{address}")
async def delete_wallet(address: str, session: AsyncSession = Depends(get_session), _: bool = Depends(role_checker)):
    wallet = await wallet_service.get_wallet_by_address(address, session)

    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    await wallet_service.delete_wallet(wallet, session)

    return {"message": "Wallet deleted successfully"}