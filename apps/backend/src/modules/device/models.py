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
    from src.modules.home.models import Home


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    __table_args__ = (
        UniqueConstraint(
            "home_id",
            "serial_number",
            name="uq_device_home_serial",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    home_id: uuid.UUID = Field(
        foreign_key="homes.id",
        nullable=False,
        index=True,
    )

    device_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(
            pg.UUID,
            nullable=False,
            unique=True,
        ),
    )

    device_code: Optional[str] = Field(default=None, max_length=100, unique=True)

    device_type: str = Field(sa_column=Column(String(30), nullable=False))

    telemetry_source: str = Field(default="PHYSICAL", max_length=20)
    counter_modulus_wh: int | None = Field(default=None, sa_type=BigInteger)

    manufacturer: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    model: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    serial_number: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    mqtt_client_id: str = Field(
        sa_column=Column(
            String(150),
            nullable=False,
            unique=True,
        )
    )

    firmware_version: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50)),
    )

    installation_date: Optional[date] = Field(
        default=None,
        sa_column=Column(Date),
    )

    status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False),
    )

    last_seen_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    home: Optional["Home"] = Relationship(
        back_populates="devices",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    credentials: list["DeviceCredential"] = Relationship(
        back_populates="device",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class DeviceCredential(SQLModel, table=True):
    __tablename__ = "device_credentials"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    device_id: uuid.UUID = Field(
        foreign_key="devices.id",
        nullable=False,
        index=True,
    )

    credential_hash: str = Field(
        sa_column=Column(
            String(128),
            nullable=False,
            unique=True,
        )
    )

    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    device: Optional["Device"] = Relationship(
        back_populates="credentials",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


# ============================================================
# TELEMETRY
# ============================================================


class TelemetryMessage(SQLModel, table=True):
    __tablename__ = "telemetry_messages"

    __table_args__ = (
        UniqueConstraint("device_id", "message_id", name="uq_telemetry_device_message"),
        UniqueConstraint(
            "device_id",
            "sequence_number",
            name="uq_telemetry_device_sequence",
        ),
        Index(
            "ix_telemetry_device_measured",
            "device_id",
            "measured_at",
        ),
        Index(
            "ix_telemetry_received_at",
            "received_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    device_id: uuid.UUID = Field(
        foreign_key="devices.id",
        nullable=False,
        index=True,
    )

    message_id: uuid.UUID | None = Field(default=None)

    sequence_number: int = Field(sa_column=Column(BigInteger, nullable=False))

    schema_version: str = Field(
        default="1",
        sa_column=Column(String(20), nullable=False),
    )

    measured_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    mqtt_topic: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255)),
    )

    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))

    quality_status: str = Field(
        default="RECEIVED",
        sa_column=Column(String(20), nullable=False),
    )

    validation_errors: Optional[list[Any]] = Field(
        default=None,
        sa_column=Column(JSONB),
    )


# ============================================================
# SMART METER
# ============================================================


class SmartMeter(SQLModel, table=True):
    __tablename__ = "smart_meter"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    telemetry_id: uuid.UUID = Field(
        foreign_key="telemetry_messages.id",
        nullable=False,
        unique=True,
    )

    voltage_v: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(10, 3)),
    )

    current_a: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(10, 3)),
    )

    frequency_hz: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(8, 3)),
    )

    active_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    consumption_power_w: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(12, 3))
    )

    power_factor: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(5, 4)),
    )

    grid_import_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    grid_export_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    cumulative_consumption_wh: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    cumulative_import_wh: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    cumulative_export_wh: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )


# ============================================================
# INVERTER
# ============================================================


class Inverter(SQLModel, table=True):
    __tablename__ = "inverter"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    telemetry_id: uuid.UUID = Field(
        foreign_key="telemetry_messages.id",
        nullable=False,
        unique=True,
    )

    dc_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    ac_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    daily_energy_wh: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    lifetime_energy_wh: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    temperature_c: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(8, 3)),
    )

    efficiency_pct: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(6, 3)),
    )

    operating_state: Optional[str] = Field(
        default=None,
        sa_column=Column(String(30)),
    )

    alarm_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )


# ============================================================
# WEATHER
# ============================================================


class WeatherSensor(SQLModel, table=True):
    __tablename__ = "weather"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    telemetry_id: uuid.UUID = Field(
        foreign_key="telemetry_messages.id",
        nullable=False,
        unique=True,
    )

    irradiance_w_m2: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(10, 3)),
    )

    ambient_temperature_c: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(8, 3)),
    )

    panel_temperature_c: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(8, 3)),
    )

    humidity_pct: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(6, 3)),
    )

    wind_speed_m_s: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(8, 3)),
    )


# ============================================================
# BATTERY
# ============================================================


class BatteryMonitor(SQLModel, table=True):
    __tablename__ = "battery"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    telemetry_id: uuid.UUID = Field(
        foreign_key="telemetry_messages.id",
        nullable=False,
        unique=True,
    )

    cumulative_charge_wh: int | None = Field(default=None, sa_type=BigInteger)
    cumulative_discharge_wh: int | None = Field(default=None, sa_type=BigInteger)
    capacity_wh: int | None = Field(default=None, sa_type=BigInteger)

    state_of_charge_pct: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(6, 3)),
    )

    voltage_v: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(10, 3)),
    )

    current_a: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(10, 3)),
    )

    charge_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    discharge_power_w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 3)),
    )

    temperature_c: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(8, 3)),
    )

    available_energy_wh: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger),
    )

    operating_state: Optional[str] = Field(
        default=None,
        sa_column=Column(String(30)),
    )


# ============================================================
# DEVICE COUNTER SNAPSHOTS
# ============================================================


class DeviceCounterSnapshot(SQLModel, table=True):
    __tablename__ = "device_counter_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "counter_name",
            name="uq_device_counter_name",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    device_id: uuid.UUID = Field(
        foreign_key="devices.id",
        nullable=False,
        index=True,
    )

    counter_name: str = Field(sa_column=Column(String(80), nullable=False))

    counter_value_wh: int = Field(sa_column=Column(BigInteger, nullable=False))

    measured_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class TelemetryAssessment(SQLModel, table=True):
    """Safe audit of accepted and rejected evidence, with counted repeated delivery."""

    __tablename__ = "telemetry_assessments"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    fingerprint: str = Field(unique=True, max_length=64)
    device_id: uuid.UUID | None = Field(
        default=None, foreign_key="devices.id", index=True
    )
    claimed_device_id: str = Field(default="", max_length=100)
    sequence_number: int | None = Field(default=None, sa_type=BigInteger)
    payload_hash: str = Field(max_length=64)
    state: str = Field(max_length=30, index=True)
    reason: str = Field(max_length=300)
    occurrences: int = 1
    first_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
