"""Canonical Device persistence with home ownership checks."""
from uuid import UUID
from sqlmodel import select
from .models import Device
from src.modules.home.service import HomeService

class DeviceService:
    async def create_device(self,user,device_data,session):
        if not await HomeService().get_home_by_id(user,device_data.home_id,session):
            raise PermissionError('Home belongs to another user')
        data=device_data.model_dump()
        data['device_type']={'SMART_METER':'smart_meter','INVERTER':'solar_inverter','BATTERY':'battery_monitor','WEATHER_SENSOR':'weather_sensor'}.get(data['device_type'],data['device_type'])
        row=Device(**data); session.add(row); await session.commit()
        return row
    async def get_devices_by_home(self,user,home_id,session):
        if not await HomeService().get_home_by_id(user,home_id,session):
            raise PermissionError('Home belongs to another user')
        return (await session.exec(select(Device).where(Device.home_id==UUID(str(home_id))))).all()
    async def get_device_by_id(self,user,device_id,session):
        row=await session.get(Device,UUID(str(device_id)))
        if row and not await HomeService().get_home_by_id(user,row.home_id,session):
            raise PermissionError('Meter belongs to another user')
        return row
    async def update_device(self,user,device_id,device_data,session):
        row=await self.get_device_by_id(user,device_id,session)
        if row:
            for key,value in device_data.model_dump(exclude_unset=True).items():
                if key=='status' and value not in ('PENDING','DISABLED'):
                    raise PermissionError('Only community operators may activate meters')
                setattr(row,key,value)
            await session.commit()
        return row
    async def delete_device(self,user,device_id,session):
        row=await self.get_device_by_id(user,device_id,session)
        if not row: return False
        row.status='DISABLED'; await session.commit()
        return True
