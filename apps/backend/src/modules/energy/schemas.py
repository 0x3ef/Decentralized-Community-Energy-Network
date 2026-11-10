"""Pydantic request and response contracts for the energy API."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnergyIntervalReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    home_id: UUID
    interval_start: datetime
    interval_end: datetime
    generation_wh: int
    consumption_wh: int
    grid_import_wh: int
    grid_export_wh: int
    battery_charge_wh: int
    battery_discharge_wh: int
    eligible_export_wh: int
    calculation_version: str
    quality_status: str


class EnergyCreditReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interval_id: UUID
    owner_id: UUID
    energy_wh: int
    token_amount: Decimal
    status: str
    created_at: datetime


class EnergySummaryModel(BaseModel):
    home_id: UUID
    from_date: datetime
    to_date: datetime
    generation_wh: int
    consumption_wh: int
    grid_import_wh: int
    grid_export_wh: int
    eligible_export_wh: int


class CreditApprovalResult(BaseModel):
    id: UUID
    status: str
    message: str
