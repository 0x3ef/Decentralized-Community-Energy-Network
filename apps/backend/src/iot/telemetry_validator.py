"""Validation of the MQTT telemetry envelope and typed payloads.

This module is the **single source of truth** for what "valid
telemetry" means. The gateway (in the ``iot/`` module) produces the
envelope; this validator decides whether it can be persisted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class SmartMeterData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    voltage_v: Decimal | None = Field(default=None, ge=0, le=1000)
    current_a: Decimal | None = Field(default=None, ge=0, le=100000)
    frequency_hz: Decimal | None = Field(default=None, ge=40, le=70)
    active_power_w: Decimal | None = Field(default=None, ge=-100000000, le=100000000)
    consumption_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    power_factor: Decimal | None = Field(default=None, ge=-1, le=1)
    grid_import_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    grid_export_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    consumption_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    grid_import_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    grid_export_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )


class SolarInverterData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    dc_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    ac_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    daily_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    lifetime_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    temperature_c: Decimal | None = Field(default=None, ge=-80, le=150)
    efficiency_pct: Decimal | None = Field(default=None, ge=0, le=100)
    operating_state: bool | None = None
    alarm_code: str | None = Field(default=None, max_length=50)


class WeatherData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    irradiance_w_m2: Decimal | None = Field(default=None, ge=0, le=1600)
    ambient_temperature_c: Decimal | None = Field(default=None, ge=-80, le=150)
    panel_temperature_c: Decimal | None = Field(default=None, ge=-80, le=150)
    relative_humidity_pct: Decimal | None = Field(default=None, ge=0, le=100)
    wind_speed_m_s: Decimal | None = Field(default=None, ge=0, le=150)


class BatteryData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    state_of_charge_pct: Decimal | None = Field(default=None, ge=0, le=100)
    battery_voltage_v: Decimal | None = Field(default=None, ge=0, le=1000)
    battery_current_a: Decimal | None = Field(default=None, ge=-100000, le=100000)
    charge_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    discharge_power_w: Decimal | None = Field(default=None, ge=0, le=100000000)
    temperature_c: Decimal | None = Field(default=None, ge=-80, le=150)
    available_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    capacity_kwh: Decimal | None = Field(
        default=None, gt=0, le=Decimal("9000000000000000")
    )
    cumulative_charge_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    cumulative_discharge_energy_kwh: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9000000000000000")
    )
    charge_efficiency_pct: Decimal | None = Field(default=None, gt=0, le=100)
    discharge_efficiency_pct: Decimal | None = Field(default=None, gt=0, le=100)
    status: str | None = None


_DATA_MODELS: dict[str, type[BaseModel]] = {
    "smart_meter": SmartMeterData,
    "solar_inverter": SolarInverterData,
    "weather_sensor": WeatherData,
    "battery_monitor": BatteryData,
}


class Envelope(BaseModel):
    """Validated telemetry envelope received from MQTT."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0", "2.0"] = "1.0"
    message_id: UUID | None = None
    community_id: UUID | None = None
    node_id: UUID | None = None
    source: Literal["PHYSICAL", "SIMULATED"] | None = None
    simulation_mode: Literal["REALTIME", "ACCELERATED", "DETERMINISTIC"] = "REALTIME"
    units: dict[str, str] | None = None
    quality: list[Literal["VALID", "SUSPECT", "INVALID", "COUNTER_RESET"]] = Field(
        default_factory=list
    )
    device_id: str = Field(min_length=1)
    home_id: str = Field(min_length=1)
    sensor_type: Literal[
        "smart_meter", "solar_inverter", "weather_sensor", "battery_monitor"
    ]
    sequence_number: int = Field(ge=0, le=2**63 - 1)
    measured_at: datetime
    data: dict[str, Any]

    @field_validator("measured_at")
    @classmethod
    def _ensure_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware")
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError) as exc:
            raise ValueError("Timestamp is outside the supported UTC range") from exc

    @model_validator(mode="after")
    def versioned_contract(self):
        if self.schema_version == "2.0":
            if any(
                value is None
                for value in (
                    self.message_id,
                    self.community_id,
                    self.node_id,
                    self.source,
                    self.units,
                )
            ):
                raise ValueError(
                    "v2 requires message, community, node, source and explicit units"
                )
            if self.units != {field: measurement_unit(field) for field in self.data}:
                raise ValueError("Units must exactly match every measurement field")
        elif self.simulation_mode != "REALTIME":
            raise ValueError("Offline simulation requires v2 provenance")
        return self

    def typed_data(self) -> BaseModel:
        """Return the typed Pydantic payload for this sensor type."""
        return _DATA_MODELS[self.sensor_type].model_validate(self.data)


def validate_envelope(
    raw: dict[str, Any],
) -> tuple[Envelope | None, list[dict[str, Any]]]:
    """Validate ``raw`` and return ``(envelope, errors)``.

    On success: ``(Envelope, [])``.
    On failure: ``(None or Envelope, [{"loc": ..., "msg": ...}, ...])``.

    The envelope is returned even when the typed payload is invalid, so
    the caller can persist the raw message with
    ``quality_status='invalid'`` and ``validation_errors`` for auditing.
    """
    try:
        envelope = Envelope.model_validate(raw)
    except ValidationError as exc:
        return None, exc.errors(include_url=False)

    try:
        envelope.typed_data()
    except ValidationError as exc:
        return envelope, exc.errors(include_url=False)

    return envelope, []


def measurement_unit(field: str) -> str:
    for suffix, unit in (
        ("_kwh", "kWh"),
        ("_w_m2", "W/m2"),
        ("_power_w", "W"),
        ("_voltage_v", "V"),
        ("_current_a", "A"),
        ("_v", "V"),
        ("_a", "A"),
        ("_hz", "Hz"),
        ("_pct", "%"),
        ("_c", "degC"),
        ("_m_s", "m/s"),
    ):
        if field.endswith(suffix):
            return unit
    return {
        "power_factor": "1",
        "operating_state": "bool",
        "alarm_code": "text",
        "status": "text",
    }.get(field, "unknown")
