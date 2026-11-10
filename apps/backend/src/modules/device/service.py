from datetime import datetime

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Device

from .schemas import DeviceCreateModel, DeviceModel, DeviceUpdateModel, DeviceCredentialIssue




class DeviceService:
    async def create_device(self, user, device_data: DeviceCreateModel, session: AsyncSession) -> DeviceModel:
        device_data_dict = device_data.model_dump()
        device_data_dict["owner_id"] = user.id

        new_device = DeviceModel(**device_data_dict)

        session.add(new_device)

        await session.commit()

        return new_device 

    async def get_devices_by_home(self, user, home_id: str, session: AsyncSession) -> list[DeviceModel]:
        statement = (
            select(DeviceModel)
            .where(DeviceModel.home_id == home_id)
            .order_by(desc(DeviceModel.created_at))
        )

        result = await session.exec(statement)

        return result.all()

    async def get_device_by_id(self, device_id: str, session: AsyncSession) -> DeviceModel | None:
        statement = select(DeviceModel).where(
            DeviceModel.id == device_id
        )

        result = await session.exec(statement)

        device = result.first()

        return device if device is not None else None

    async def update_device(self, user, device_id: str, device_data: DeviceUpdateModel, session: AsyncSession) -> DeviceModel | None:
        device = await self.get_device_by_id(user, device_id, session)

        if device is None:
            return None

        device_data_dict = device_data.model_dump(exclude_unset=True)

        for field, value in device_data_dict.items():
            setattr(device, field, value)

        await session.commit()

        return device

    async def delete_device(self, user, device_id: str, session: AsyncSession) -> bool:
        device = await self.get_device_by_id(user, device_id, session)

        if device is None:
            return False

        await session.delete(device)
        await session.commit()

        return True