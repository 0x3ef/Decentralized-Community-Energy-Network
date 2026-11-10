from datetime import datetime

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Home

from .schemas import HomeCreateModel, HomeModel, HomeUpdateModel



class HomeService:
    async def create_home(self, user, home_data: HomeCreateModel, session: AsyncSession) -> HomeModel:
        home_data_dict = home_data.model_dump()
        home_data_dict["owner_id"] = user.id

        new_home = HomeModel(**home_data_dict)

        session.add(new_home)

        await session.commit()

        return new_home

    async def get_homes_by_user(self, user, session: AsyncSession) -> list[HomeModel]:
        statement = (
            select(HomeModel)
            .where(HomeModel.owner_id == user.id)
            .order_by(desc(HomeModel.created_at))
        )

        result = await session.exec(statement)

        return result.all()

    async def get_home_by_id(self, user, home_id: str, session: AsyncSession) -> HomeModel | None:
        statement = select(HomeModel).where(
            HomeModel.id == home_id,
            HomeModel.owner_id == user.id
        )

        result = await session.exec(statement)

        home = result.first()

        return home if home is not None else None

    async def update_home(self, user, home_id: str, home_data: HomeUpdateModel, session: AsyncSession) -> HomeModel | None:
        home = await self.get_home_by_id(user, home_id, session)

        if home is None:
            return None

        home_data_dict = home_data.model_dump(exclude_unset=True)

        for field, value in home_data_dict.items():
            setattr(home, field, value)

        await session.commit()

        return home

    async def delete_home(self, user, home_id: str, session: AsyncSession) -> bool:
        home = await self.get_home_by_id(user, home_id, session)

        if home is None:
            return False

        await session.delete(home)
        await session.commit()

        return True