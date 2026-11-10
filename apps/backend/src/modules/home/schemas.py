import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class HomeCreateModel(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=3, max_length=255)
    city: str
    country: str = "Colombia"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = "Russia/Moscow"
    installed_capacity_w: int = Field(default=0, ge=0)
    has_battery: bool = False

class HomeUpdateModel(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    installed_capacity_w: int | None = Field(default=None, ge=0)
    has_battery: bool | None = None
    status: str | None = None

class HomeModel(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    address: str
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    timezone: str
    installed_capacity_w: int
    has_battery: bool
    status: str
    created_at: datetime
