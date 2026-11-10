"""Domain model for simulated IoT devices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SensorType(StrEnum):
    """Supported IoT sensor types."""

    SMART_METER = "smart_meter"
    SOLAR_INVERTER = "solar_inverter"
    WEATHER_SENSOR = "weather_sensor"
    BATTERY_MONITOR = "battery_monitor"


class SensorStatus(StrEnum):
    """Device operational states."""

    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class Sensor:
    """An IoT device installed in a home.

    Args:
        device_code: Unique identifier of the physical device.
        sensor_type: Category of the sensor.
        home_id: Identifier of the home that owns the device.
        status: Whether the device is currently emitting telemetry.

    Raises:
        ValueError: If ``device_code`` or ``home_id`` is empty.
    """

    device_code: str
    sensor_type: SensorType
    home_id: str
    status: SensorStatus = SensorStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.device_code.strip():
            raise ValueError("device_code cannot be empty")
        if not self.home_id.strip():
            raise ValueError("home_id cannot be empty")

    @property
    def is_active(self) -> bool:
        """Return ``True`` when the device is active."""
        return self.status == SensorStatus.ACTIVE

    def get_mqtt_topic(self) -> str:
        """Return the canonical MQTT topic for this device.

        The format ``solar/<home_id>/<device_code>/telemetry`` is
        compatible with local Mosquitto topic rules.
        """
        return f"solar/{self.home_id}/{self.device_code}/telemetry"
