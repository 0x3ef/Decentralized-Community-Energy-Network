import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.modules.auth.models import User
    from src.modules.device.models import Device
    from src.modules.energy.models import EnergyInterval


class Home(SQLModel, table=True):
    __tablename__ = "homes"

    __table_args__ = (
        CheckConstraint(
            "installed_capacity_w >= 0",
            name="ck_home_capacity_nonnegative",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_home_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_home_longitude_range",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    owner_id: uuid.UUID = Field(
        foreign_key="users.uid",
        nullable=False,
        index=True,
    )

    address: str = Field(
        sa_column=Column(String(255), nullable=False)
    )

    city: str = Field(
        sa_column=Column(String(100), nullable=False)
    )

    country: str = Field(
        default="Colombia",
        sa_column=Column(String(100), nullable=False),
    )

    latitude: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(9, 6)),
    )

    longitude: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(9, 6)),
    )

    timezone: str = Field(
        default="America/Bogota",
        sa_column=Column(String(60), nullable=False),
    )

    installed_capacity_w: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )

    has_battery: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False),
    )

    status: str = Field(
        default="ACTIVE",
        sa_column=Column(String(20), nullable=False),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    owner: Optional["User"] = Relationship(
        back_populates="home",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    devices: list["Device"] = Relationship(
        back_populates="home",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    intervals: list["EnergyInterval"] = Relationship(
        back_populates="home",
       sa_relationship_kwargs={"lazy": "selectin"},
    )
