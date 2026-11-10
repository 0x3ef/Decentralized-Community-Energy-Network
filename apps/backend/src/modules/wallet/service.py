from datetime import datetime

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Wallet

from .schemas import WalletCreateModel, WalletModel


class WalletService:

    async def get_wallets_by_user(self, user, session: AsyncSession) -> list[WalletModel]:
        statement = (
            select(Wallet)
            .where(Wallet.user_id == user.id)
            .order_by(desc(Wallet.created_at))
        )

        result = await session.exec(statement)

        return result.all()

    async def get_wallet_by_address(self, address: str, session: AsyncSession) -> WalletModel | None:
        statement = select(Wallet).where(Wallet.address == address)

        result = await session.exec(statement)

        wallet = result.first()

        return wallet if wallet is not None else None
    
    async def create_wallet(self, wallet_data: WalletCreateModel, session: AsyncSession) -> WalletModel:
        wallet_data_dict = wallet_data.model_dump()

        new_wallet = Wallet(**wallet_data_dict)

        session.add(new_wallet)

        await session.commit()

        return new_wallet

    async def delete_wallet(self, address: str, session: AsyncSession) -> None:
        wallet = await self.get_wallet_by_address(address, session)

        if wallet is not None:
            await session.delete(wallet)

        await session.commit()

        return None