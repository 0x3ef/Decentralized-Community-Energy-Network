"""Wallet linking requires proof of possession via the community challenge API."""
from fastapi import APIRouter, Depends
from sqlmodel import select
from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from .models import Wallet

wallet_router = APIRouter()

@wallet_router.get("/")
async def my_wallets(user=Depends(get_current_user), session=Depends(get_session)):
    return {"wallets": (await session.exec(select(Wallet).where(Wallet.user_id == user.uid))).all()}
