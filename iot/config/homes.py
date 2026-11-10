"""Declarative home catalogue.

Adding a home is a one-liner: call :func:`build_home` with the desired
parameters. Sensor codes are derived from the home id and the sensor
type, and follow the same convention as ``database/seeds/03_devices.sql``
so that the simulator produces telemetry for devices that are already
registered in the database.

Convention: ``<PREFIX>-<CITY>-<home_suffix>-<index>``
    HOME-MS-001 + SM  + 1 → SM-MS-001-001
    HOME-MS-001 + INV + 2 → INV-MS-001-002
    HOME-MS-001 + WS  + 3 → WS-MS-001-003
    HOME-MS-001 + BM  + 4 → BM-MS-001-004
"""

from __future__ import annotations

from decimal import Decimal

from models.home import Home
from models.sensor import Sensor, SensorType

_PREFIX: dict[SensorType, str] = {
    SensorType.SMART_METER: "SM",
    SensorType.SOLAR_INVERTER: "INV",
    SensorType.WEATHER_SENSOR: "WS",
    SensorType.BATTERY_MONITOR: "BM",
}


def _make_sensor(
    home_id: str, sensor_type: SensorType, index: int
) -> Sensor:
    """Build a :class:`Sensor` whose code matches the seed convention.

    The city segment is extracted from the home id: ``HOME-MS-001``
    becomes ``MS``. The home suffix is everything after the last ``-``
    in ``home_id``.
    """
    parts = home_id.split("-")
    city = parts[1]          # HOME-MS-001 → MS
    suffix = parts[-1]       # HOME-MS-001 → 001
    return Sensor(
        device_code=f"{_PREFIX[sensor_type]}-{city}-{suffix}-{index:03d}",
        sensor_type=sensor_type,
        home_id=home_id,
    )


def build_home(
    home_id: str,
    city: str,
    solar_kw: float,
    battery_kwh: float,
) -> Home:
    """Create a :class:`Home` with the appropriate sensors.

    A solar inverter is only added when ``solar_kw > 0`` and a battery
    monitor is only added when ``battery_kwh > 0``. This mirrors the
    physical reality: a home without PV has no inverter, and a home
    without storage has no battery monitor.
    """
    devices: list[Sensor] = []
    for index, sensor_type in enumerate(SensorType, start=1):
        if sensor_type == SensorType.SOLAR_INVERTER and solar_kw <= 0:
            continue
        if (
            sensor_type == SensorType.BATTERY_MONITOR
            and battery_kwh <= 0
        ):
            continue
        devices.append(_make_sensor(home_id, sensor_type, index))

    return Home(
        home_id=home_id,
        city=city,
        solar_capacity_kw=Decimal(str(solar_kw)),
        battery_capacity_kwh=Decimal(str(battery_kwh)),
        devices=tuple(devices),
    )


def build_default_homes() -> list[Home]:
    """Return the demo community used for local testing.

    Every home is a prosumer: it can produce and consume at the same
    time. The parameters describe installed capacity, not the role the
    home plays in the market. Whether a home sells or buys in a given
    interval is decided by its net balance, not by its configuration.
    """
    return [
        # 4 kW PV + 10 kWh battery → SM, INV, WS, BM
        build_home("HOME-MS-001", "Moscow", solar_kw=4, battery_kwh=10),
        # 6 kW PV, no battery → SM, INV, WS
        build_home("HOME-MS-002", "Moscow", solar_kw=6, battery_kwh=0),
        # No PV, no battery → SM, WS
        build_home("HOME-MS-003", "Moscow", solar_kw=0, battery_kwh=0),
        # No PV, 5 kWh battery → SM, WS, BM
        build_home("HOME-MS-004", "Moscow", solar_kw=0, battery_kwh=5),
        # 3 kW PV, no battery → SM, INV, WS
        build_home("HOME-MS-005", "Moscow", solar_kw=3, battery_kwh=0),
    ]
