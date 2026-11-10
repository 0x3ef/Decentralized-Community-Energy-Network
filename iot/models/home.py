"""Domain model for a simulated energy home."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.sensor import Sensor


@dataclass(frozen=True, slots=True)
class Home:
    """A residential installation in the energy community.

    Args:
        home_id: Unique identifier of the home.
        city: City where the installation lives.
        solar_capacity_kw: Installed PV capacity in kilowatts.
        battery_capacity_kwh: Installed battery capacity in kWh.
        devices: Tuple of sensors installed in the home.

    Raises:
        ValueError: If IDs are empty, capacities negative, or two
            devices share the same code.
    """

    home_id: str
    city: str
    solar_capacity_kw: Decimal
    battery_capacity_kwh: Decimal
    devices: tuple[Sensor, ...]

    def __post_init__(self) -> None:
        if not self.home_id.strip():
            raise ValueError("home_id cannot be empty")
        if not self.city.strip():
            raise ValueError("city cannot be empty")
        if self.solar_capacity_kw < 0:
            raise ValueError("solar_capacity_kw cannot be negative")
        if self.battery_capacity_kwh < 0:
            raise ValueError("battery_capacity_kwh cannot be negative")

        codes = [device.device_code for device in self.devices]
        if len(codes) != len(set(codes)):
            raise ValueError(
                f"Duplicate devices found in home {self.home_id}"
            )

    @property
    def has_solar(self) -> bool:
        """Return ``True`` when the home has PV generation."""
        return self.solar_capacity_kw > 0

    @property
    def has_battery(self) -> bool:
        """Return ``True`` when the home has battery storage."""
        return self.battery_capacity_kwh > 0

    def get_device(self, device_code: str) -> Sensor:
        """Retrieve a device by its unique code.

        Raises:
            ValueError: If no device with ``device_code`` exists.
        """
        for device in self.devices:
            if device.device_code == device_code:
                return device
        raise ValueError(
            f"Device {device_code} not found in home {self.home_id}"
        )
