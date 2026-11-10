"""Approximate, explicitly simulated Colombian home energy physics.

A location/date-dependent solar-elevation approximation and shared power balance
feed every sensor. Decimal counters integrate actual elapsed UTC time. This is
not an irradiance forecast, calibrated meter, or regulatory settlement model.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import cos, pi, radians, sin
from random import Random
from zoneinfo import ZoneInfo

from models.home import Home


def as_decimal(value):
    return Decimal(str(value))


@dataclass(frozen=True)
class HomeProfile:
    usage: str = "residential"
    appliance_w: Decimal = Decimal(600)
    latitude: float = 3.45
    longitude: float = -76.53
    timezone: str = "America/Bogota"
    baseline_w: Decimal = Decimal(350)
    peak_w: Decimal = Decimal(1400)
    occupancy: Decimal = Decimal(1)
    min_soc: Decimal = Decimal("0.1")
    max_soc: Decimal = Decimal("0.95")
    charge_efficiency: Decimal = Decimal("0.95")
    discharge_efficiency: Decimal = Decimal("0.95")
    max_battery_w: Decimal = Decimal(3000)
    pv_efficiency: Decimal = Decimal("0.96")

    def __post_init__(self):
        if self.usage not in ("residential", "producer", "commercial"):
            raise ValueError("Unknown load usage")
        ZoneInfo(self.timezone)
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("Invalid geographic coordinates")
        if not 0 <= self.min_soc < self.max_soc <= 1:
            raise ValueError("Invalid battery SOC bounds")
        if not all(
            0 < value <= 1
            for value in (
                self.charge_efficiency,
                self.discharge_efficiency,
                self.pv_efficiency,
            )
        ):
            raise ValueError("Efficiency must be within (0,1]")
        if (
            min(
                self.baseline_w,
                self.peak_w,
                self.occupancy,
                self.max_battery_w,
                self.appliance_w,
            )
            < 0
        ):
            raise ValueError("Profile powers and occupancy must be nonnegative")


class HomeEnergyModel:
    def __init__(
        self, home: Home, profile: HomeProfile | None = None, seed: int | None = None
    ):
        self.home = home
        self.profile = profile or HomeProfile()
        self.rng = Random(seed)
        self.previous: datetime | None = None
        self.counters = {
            key: Decimal(0)
            for key in (
                "generation",
                "consumption",
                "import",
                "export",
                "charge",
                "discharge",
            )
        }
        self.stored = home.battery_capacity_kwh * min(
            self.profile.max_soc, max(self.profile.min_soc, Decimal("0.5"))
        )
        self.daily_generation = Decimal(0)
        self.day = None
        self.state: dict = {}

    def solar_factor(self, at: datetime) -> float:
        if at.tzinfo is None:
            raise ValueError("Simulation timestamps must be timezone-aware")
        local = at.astimezone(ZoneInfo(self.profile.timezone))
        day = local.timetuple().tm_yday
        declination = radians(23.44) * sin(2 * pi * (day - 81) / 365.2425)
        # Solar time uses UTC longitude correction and approximate equation of time.
        b = 2 * pi * (day - 81) / 364
        equation = 9.87 * sin(2 * b) - 7.53 * cos(b) - 1.5 * sin(b)
        utc = at.astimezone(UTC)
        hour = (
            utc.hour
            + utc.minute / 60
            + utc.second / 3600
            + self.profile.longitude / 15
            + equation / 60
        )
        angle = radians(15 * (hour - 12))
        lat = radians(self.profile.latitude)
        return max(
            0, sin(lat) * sin(declination) + cos(lat) * cos(declination) * cos(angle)
        )

    def step(self, at: datetime) -> dict:
        if at.tzinfo is None:
            raise ValueError("Simulation timestamps must be timezone-aware")
        at = at.astimezone(UTC)
        if self.previous == at:
            return self.state
        if self.previous and at < self.previous:
            raise ValueError("Simulation clock cannot regress")
        if self.previous and (at - self.previous) > timedelta(seconds=60):
            while at - self.previous > timedelta(seconds=60):
                self.step(self.previous + timedelta(seconds=60))
        elapsed = (
            as_decimal((at - self.previous).total_seconds())
            if self.previous
            else Decimal(0)
        )
        hours = elapsed / 3600
        p = self.profile
        local = at.astimezone(ZoneInfo(p.timezone))
        hour = local.hour + local.minute / 60
        cloud = self.state.get("cloud", Decimal(1)) * Decimal("0.8") + as_decimal(
            self.rng.uniform(0.55, 1)
        ) * Decimal("0.2")
        solar = as_decimal(self.solar_factor(at)) * cloud
        generation = self.home.solar_capacity_kw * 1000 * solar * p.pv_efficiency
        morning = as_decimal(max(0, 1 - abs(hour - 7) / 2))
        evening = as_decimal(max(0, 1 - abs(hour - 19) / 3))
        weekend = Decimal("1.15") if local.weekday() >= 5 else Decimal(1)
        load = (
            (p.baseline_w + p.peak_w * (morning + evening) * p.occupancy)
            * weekend
            * as_decimal(self.rng.uniform(0.9, 1.1))
        )
        if p.usage == "commercial":
            load = p.baseline_w + (
                p.peak_w if local.weekday() < 5 and 8 <= hour < 18 else Decimal(0)
            )
        if self.rng.random() < 0.12:
            load += p.appliance_w
        charge = discharge = Decimal(0)
        capacity = self.home.battery_capacity_kwh
        surplus = generation - load
        if capacity and hours > 0:
            if surplus > 0:
                charge = min(
                    surplus,
                    p.max_battery_w,
                    max(
                        Decimal(0),
                        (capacity * p.max_soc - self.stored)
                        * 1000
                        / (hours * p.charge_efficiency),
                    ),
                )
                self.stored += charge * hours * p.charge_efficiency / 1000
            else:
                discharge = min(
                    -surplus,
                    p.max_battery_w,
                    max(
                        Decimal(0),
                        (self.stored - capacity * p.min_soc)
                        * 1000
                        * p.discharge_efficiency
                        / hours,
                    ),
                )
                self.stored -= discharge * hours / (1000 * p.discharge_efficiency)
        net = generation + discharge - load - charge
        flows = {
            "generation": generation,
            "consumption": load,
            "import": max(-net, Decimal(0)),
            "export": max(net, Decimal(0)),
            "charge": charge,
            "discharge": discharge,
        }
        for name, power in flows.items():
            self.counters[name] += power * hours / 1000
        if self.day != local.date():
            self.daily_generation = Decimal(0)
            self.day = local.date()
        self.daily_generation += generation * hours / 1000
        self.previous = at
        self.state = {
            **flows,
            "cloud": cloud,
            "soc": self.stored / capacity * 100 if capacity else Decimal(0),
            "irradiance": solar * 1000,
            "temperature": Decimal(24) + solar * 20,
        }
        return self.state

    def reading(self, kind: str, at: datetime) -> dict:
        s = self.step(at)
        c = self.counters
        if kind == "smart_meter":
            return dict(
                voltage_v=120,
                current_a=abs(s["import"] - s["export"]) / 120,
                frequency_hz=60,
                active_power_w=s["import"] - s["export"],
                consumption_power_w=s["consumption"],
                power_factor=1,
                grid_import_power_w=s["import"],
                grid_export_power_w=s["export"],
                consumption_energy_kwh=c["consumption"],
                grid_import_energy_kwh=c["import"],
                grid_export_energy_kwh=c["export"],
            )
        if kind == "solar_inverter":
            return dict(
                dc_power_w=s["generation"] / self.profile.pv_efficiency,
                ac_power_w=s["generation"],
                daily_energy_kwh=self.daily_generation,
                lifetime_energy_kwh=c["generation"],
                temperature_c=s["temperature"],
                efficiency_pct=self.profile.pv_efficiency * 100,
                operating_state=s["generation"] > 0,
                alarm_code="",
            )
        if kind == "battery_monitor":
            return dict(
                state_of_charge_pct=s["soc"],
                capacity_kwh=self.home.battery_capacity_kwh,
                cumulative_charge_energy_kwh=c["charge"],
                cumulative_discharge_energy_kwh=c["discharge"],
                charge_efficiency_pct=self.profile.charge_efficiency * 100,
                discharge_efficiency_pct=self.profile.discharge_efficiency * 100,
                battery_voltage_v=52,
                battery_current_a=(s["charge"] - s["discharge"]) / 52,
                charge_power_w=s["charge"],
                discharge_power_w=s["discharge"],
                temperature_c=25,
                available_energy_kwh=self.stored,
            )
        return dict(
            irradiance_w_m2=s["irradiance"],
            ambient_temperature_c=24,
            panel_temperature_c=s["temperature"],
            relative_humidity_pct=65,
            wind_speed_m_s=2,
        )


def profile_for(kind: str, **overrides) -> HomeProfile:
    defaults = {
        "consumer": {},
        "solar_producer": {
            "usage": "producer",
            "baseline_w": Decimal(40),
            "peak_w": Decimal(100),
            "appliance_w": Decimal(0),
        },
        "prosumer": {},
        "battery_prosumer": {},
        "commercial": {
            "usage": "commercial",
            "baseline_w": Decimal(1200),
            "peak_w": Decimal(6000),
            "appliance_w": Decimal(2000),
        },
    }
    if kind not in defaults:
        raise ValueError("Unknown home profile")
    return HomeProfile(**{**defaults[kind], **overrides})
