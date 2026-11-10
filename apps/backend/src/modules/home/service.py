"""Home ownership is checked on every read and write."""
from uuid import UUID
from sqlmodel import select
from .models import Home

class HomeService:
    async def create_home(self, user, home_data, session):
        data=home_data.model_dump()
        row=Home(owner_id=user.uid,**data)
        session.add(row); await session.commit()
        return row
    async def get_homes_by_user(self,user,session):
        return (await session.exec(select(Home).where(Home.owner_id==user.uid))).all()
    async def get_home_by_id(self,user,home_id,session):
        return (await session.exec(select(Home).where(Home.id==UUID(str(home_id)),Home.owner_id==user.uid))).first()
    async def update_home(self,user,home_id,home_data,session):
        row=await self.get_home_by_id(user,home_id,session)
        if row:
            for key,value in home_data.model_dump(exclude_unset=True).items():
                setattr(row,key,value)
            await session.commit()
        return row
    async def delete_home(self,user,home_id,session):
        row=await self.get_home_by_id(user,home_id,session)
        if not row: return False
        await session.delete(row); await session.commit()
        return True
