from uuid import UUID
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class DeviceCreateModel(BaseModel):
    home_id: UUID
    device_code: str = Field(min_length=1, max_length=100)
    device_type: str = Field(pattern="^(SMART_METER|INVERTER|BATTERY)$")
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    mqtt_client_id: str = Field(min_length=1, max_length=150)

class DeviceModel(BaseModel):
    id: UUID
    home_id: UUID
    device_code: str
    device_type: str
    manufacturer: str | None
    model: str | None
    mqtt_client_id: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime

class DeviceUpdateModel(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    installed_capacity_w: int | None = Field(default=None, ge=0)
    has_battery: bool | None = None
    status: str | None = None

class DeviceCredentialIssue(BaseModel):
    credential: str
    expires_at: datetime | None

class TelemetryIngest(BaseModel):
    device_code: str
    sequence_number: int = Field(ge=0)
    schema_version: str = "1"
    measured_at: datetime
    payload: dict

class TelemetryModel(BaseModel):
    id: UUID
    device_id: UUID
    sequence_number: int
    measured_at: datetime
    received_at: datetime
    payload: dict
    quality_status: str
