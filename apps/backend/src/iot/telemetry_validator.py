"""Validation of the MQTT telemetry envelope and typed payloads.

This module is the **single source of truth** for what "valid
telemetry" means. The gateway (in the ``iot/`` module) produces the
envelope; this validator decides whether it can be persisted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class SmartMeterData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    voltage_v: Decimal | None = Field(default=None, ge=0)
    current_a: Decimal | None = Field(default=None, ge=0)
    frequency_hz: Decimal | None = None
    active_power_w: Decimal | None = None
    power_factor: Decimal | None = Field(default=None, ge=-1, le=1)
    grid_import_power_w: Decimal | None = Field(default=None, ge=0)
    grid_export_power_w: Decimal | None = Field(default=None, ge=0)
    consumption_energy_kwh: Decimal | None = Field(default=None, ge=0)
    grid_import_energy_kwh: Decimal | None = Field(default=None, ge=0)
    grid_export_energy_kwh: Decimal | None = Field(default=None, ge=0)


class SolarInverterData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    dc_power_w: Decimal | None = Field(default=None, ge=0)
    ac_power_w: Decimal | None = Field(default=None, ge=0)
    daily_energy_kwh: Decimal | None = Field(default=None, ge=0)
    lifetime_energy_kwh: Decimal | None = Field(default=None, ge=0)
    temperature_c: Decimal | None = None
    efficiency_pct: Decimal | None = Field(default=None, ge=0, le=100)
    operating_state: bool | None = None
    alarm_code: str | None = None


class WeatherData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    irradiance_w_m2: Decimal | None = Field(default=None, ge=0)
    ambient_temperature_c: Decimal | None = None
    panel_temperature_c: Decimal | None = None
    relative_humidity_pct: Decimal | None = Field(default=None, ge=0, le=100)
    wind_speed_m_s: Decimal | None = Field(default=None, ge=0)


class BatteryData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    state_of_charge_pct: Decimal | None = Field(default=None, ge=0, le=100)
    battery_voltage_v: Decimal | None = None
    battery_current_a: Decimal | None = None
    charge_power_w: Decimal | None = Field(default=None, ge=0)
    discharge_power_w: Decimal | None = Field(default=None, ge=0)
    temperature_c: Decimal | None = None
    available_energy_kwh: Decimal | None = Field(default=None, ge=0)
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

    schema_version: Literal["1.0"] = "1.0"
    device_id: str = Field(min_length=1)
    home_id: str = Field(min_length=1)
    sensor_type: Literal[
        "smart_meter", "solar_inverter", "weather_sensor", "battery_monitor"
    ]
    sequence_number: int = Field(ge=0)
    measured_at: datetime
    data: dict[str, Any]

    @field_validator("measured_at")
    @classmethod
    def _ensure_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware")
        return value.astimezone(UTC)

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
