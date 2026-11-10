"""Energy business rules and authorization."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.energy.repository import EnergyRepository
from src.modules.home.models import Home


class EnergyService:
    """Coordinate energy reads and credit approval."""

    def __init__(self) -> None:
        self.repository = EnergyRepository()

    async def _ensure_home_access(
        self, session: AsyncSession, user, home_id: UUID
    ) -> Home:
        home = await session.get(Home, home_id)
        if home is None:
            raise LookupError("Home not found")
        if home.owner_id != user.uid and user.role not in ("admin", "operator"):
            raise PermissionError("You do not have access to this home")
        return home

    async def list_intervals(
        self, user, home_id: UUID, start: datetime, end: datetime,
        session: AsyncSession,
    ):
        if start >= end:
            raise ValueError("start must be earlier than end")
        await self._ensure_home_access(session, user, home_id)
        return await self.repository.list_intervals(
            session, home_id, start, end
        )

    async def summary(
        self, user, home_id: UUID, start: datetime, end: datetime,
        session: AsyncSession,
    ):
        if start >= end:
            raise ValueError("start must be earlier than end")
        await self._ensure_home_access(session, user, home_id)
        totals = await self.repository.summary(session, home_id, start, end)
        return {
            "home_id": home_id,
            "from_date": start,
            "to_date": end,
            **totals,
        }

    async def credits(self, user, session: AsyncSession):
        return await self.repository.list_credits(session, user.uid)

    async def credit(self, user, credit_id: UUID, session: AsyncSession):
        credit = await self.repository.get_credit(session, credit_id)
        if credit is None:
            return None
        if credit.owner_id != user.uid and user.role not in ("admin", "operator"):
            raise PermissionError("You do not have access to this credit")
        return credit

    async def approve_credit(
        self, actor, credit_id: UUID, session: AsyncSession
    ):
        from src.modules.community.service import CommunityService
        credit = await CommunityService().approve_credit(session, actor, credit_id)
        await session.commit()
        return credit
