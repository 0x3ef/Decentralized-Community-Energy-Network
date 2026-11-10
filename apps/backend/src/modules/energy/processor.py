"""Convert validated device telemetry into 15-minute energy intervals."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.device.models import (
    BatteryMonitor,
    Device,
    DeviceCounterSnapshot,
    Inverter,
    SmartMeter,
    TelemetryMessage,
)
from src.modules.energy.calculator import EnergyCalculator
from src.modules.energy.models import EnergyCredit, EnergyInterval
from src.modules.home.models import Home

from src.modules.energy.models import EnergyPowerSnapshot

logger = logging.getLogger(__name__)

# Business assumption: one SUN represents one kWh of eligible exported energy.
SUN_PER_KWH = Decimal("1")
INTERVAL_MINUTES = 15


class EnergyProcessor:
    """Process persisted telemetry idempotently using device counter snapshots."""

    def __init__(self) -> None:
        self.calculator = EnergyCalculator()

    async def process_pending(self, session: AsyncSession, limit: int = 200) -> int:
        statement = (
            select(TelemetryMessage)
            .where(TelemetryMessage.quality_status == "valid")
            .order_by(TelemetryMessage.measured_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.exec(statement)
        messages = list(result.all())
        processed = 0

        for message in messages:
            # Counter snapshots and interval increments must commit together.
            # If processing fails, the whole batch rolls back and can be retried.
            try:
                async with session.begin_nested():
                    await self._process_message(session, message)
                message.quality_status = "PROCESSED"
                processed += 1
            except ValueError as exc:
                message.quality_status = "REJECTED"
                message.validation_errors = [{"reason": str(exc)}]
                logger.warning("Rejected energy sample %s: %s", message.id, exc)
        await session.commit()
        return processed

    async def _process_message(
        self, session: AsyncSession, message: TelemetryMessage
    ) -> None:
        device = (
            await session.exec(
                select(Device).where(Device.id == message.device_id).with_for_update()
            )
        ).one()
        if device is None:
            raise ValueError("Telemetry references an unknown device")
        home = await session.get(Home, device.home_id)
        if home is None:
            raise ValueError("Device references an unknown home")

        if device.status != "ACTIVE":
            raise ValueError("Meter authorization revoked")
        envelope = message.payload or {}
        sensor_type = envelope.get("sensor_type")
        data = envelope.get("data") or {}
        deltas = {
            "generation_wh": 0,
            "consumption_wh": 0,
            "grid_import_wh": 0,
            "grid_export_wh": 0,
            "battery_charge_wh": 0,
            "battery_discharge_wh": 0,
        }

        if sensor_type == "solar_inverter":
            reading = await self._reading(session, Inverter, message.id)
            if reading and reading.lifetime_energy_wh is not None:
                deltas["generation_wh"] = await self._counter_delta(
                    session,
                    device.id,
                    "lifetime_generation",
                    int(reading.lifetime_energy_wh),
                    message.measured_at,
                )
        elif sensor_type == "smart_meter":
            reading = await self._reading(session, SmartMeter, message.id)
            if reading:
                for field, counter_name, output_name in (
                    ("cumulative_consumption_wh", "consumption", "consumption_wh"),
                    ("cumulative_import_wh", "grid_import", "grid_import_wh"),
                    ("cumulative_export_wh", "grid_export", "grid_export_wh"),
                ):
                    value = getattr(reading, field)
                    if value is not None:
                        deltas[output_name] = await self._counter_delta(
                            session,
                            device.id,
                            counter_name,
                            int(value),
                            message.measured_at,
                        )

        if sensor_type == "battery_monitor":
            reading = await self._reading(session, BatteryMonitor, message.id)
            if reading:
                for field in ("charge", "discharge"):
                    power = getattr(reading, f"{field}_power_w")
                    if power is not None:
                        deltas[f"battery_{field}_wh"] = await self._power_delta(
                            session, device.id, field, power, message.measured_at
                        )

        start, end = self.calculator.interval_bounds(
            message.measured_at - timedelta(microseconds=1), INTERVAL_MINUTES
        )
        interval_result = await session.exec(
            select(EnergyInterval)
            .where(
                EnergyInterval.home_id == home.id,
                EnergyInterval.interval_start == start,
                EnergyInterval.interval_end == end,
            )
            .with_for_update()
        )
        interval = interval_result.first()
        if interval is None:
            interval = EnergyInterval(
                home_id=home.id,
                interval_start=start,
                interval_end=end,
                quality_status="OPEN",
            )
            session.add(interval)
            await session.flush()

        if interval.quality_status != "OPEN":
            raise ValueError(
                "Late reading for finalized interval requires an explicit adjustment"
            )
        interval.generation_wh += deltas["generation_wh"]
        interval.consumption_wh += deltas["consumption_wh"]
        interval.grid_import_wh += deltas["grid_import_wh"]
        interval.grid_export_wh += deltas["grid_export_wh"]
        interval.battery_charge_wh += deltas["battery_charge_wh"]
        interval.battery_discharge_wh += deltas["battery_discharge_wh"]
        interval.eligible_export_wh = self.calculator.eligible_export(
            interval.generation_wh,
            interval.consumption_wh,
            interval.grid_export_wh,
        )
        interval.calculation_version = self.calculator.VERSION

    async def _reading(self, session, model, telemetry_id):
        result = await session.exec(
            select(model).where(model.telemetry_id == telemetry_id)
        )
        return result.first()

    async def _counter_delta(
        self, session, device_id, counter_name, current_value, measured_at
    ) -> int:
        result = await session.exec(
            select(DeviceCounterSnapshot)
            .where(
                DeviceCounterSnapshot.device_id == device_id,
                DeviceCounterSnapshot.counter_name == counter_name,
            )
            .with_for_update()
        )
        snapshot = result.first()
        if snapshot is None:
            session.add(
                DeviceCounterSnapshot(
                    device_id=device_id,
                    counter_name=counter_name,
                    counter_value_wh=current_value,
                    measured_at=measured_at,
                )
            )
            return 0

        if measured_at <= snapshot.measured_at:
            raise ValueError("Out-of-order counter reading")
        interval_start, interval_end = self.calculator.interval_bounds(
            measured_at - timedelta(microseconds=1), INTERVAL_MINUTES
        )
        if snapshot.measured_at < interval_start:
            logger.warning("Counter gap: establishing baseline without energy credit, device=%s channel=%s", device_id,counter_name)
            snapshot.counter_value_wh=current_value
            snapshot.measured_at=measured_at
            return 0
        delta = self.calculator.counter_delta(snapshot.counter_value_wh, current_value)
        from src.core.config import Config
        elapsed=Decimal(str((measured_at-snapshot.measured_at).total_seconds()))
        if Decimal(delta)>Decimal(Config.MAX_METER_POWER_W)*elapsed/3600+2:
            raise ValueError("Counter spike exceeds configured maximum meter power")
        if current_value < snapshot.counter_value_wh:
            logger.warning(
                "Counter reset detected: device=%s counter=%s",
                device_id,
                counter_name,
            )
        snapshot.counter_value_wh = current_value
        snapshot.measured_at = measured_at
        snapshot.updated_at = datetime.now(timezone.utc)
        return delta

    async def _power_delta(
        self,
        session: AsyncSession,
        device_id,
        channel: str,
        power: Decimal,
        measured_at: datetime,
    ) -> int:
        snapshot = await session.get(EnergyPowerSnapshot, (device_id, channel))
        if snapshot is None:
            session.add(
                EnergyPowerSnapshot(
                    device_id=device_id,
                    channel=channel,
                    power_w=power,
                    measured_at=measured_at,
                )
            )
            return 0
        start, _ = self.calculator.interval_bounds(
            measured_at - timedelta(microseconds=1), INTERVAL_MINUTES
        )
        if measured_at <= snapshot.measured_at or snapshot.measured_at < start:
            raise ValueError(
                "Battery sample is out-of-order or crosses an unobserved interval boundary"
            )
        elapsed = measured_at - snapshot.measured_at
        seconds = (
            Decimal(elapsed.days * 86400 + elapsed.seconds)
            + Decimal(elapsed.microseconds) / 1000000
        )
        energy = (snapshot.power_w + power) / 2 * seconds / 3600
        snapshot.power_w = power
        snapshot.measured_at = measured_at
        return int(energy)

    async def finalize_closed_intervals(
        self, session: AsyncSession, limit: int = 200
    ) -> int:
        """Create one pending energy credit after an interval has ended."""
        now = datetime.now(timezone.utc)
        result = await session.exec(
            select(EnergyInterval)
            .where(
                EnergyInterval.interval_end <= now - timedelta(minutes=2),
                EnergyInterval.quality_status == "OPEN",
            )
            .order_by(EnergyInterval.interval_end)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        intervals = list(result.all())
        created = 0

        for interval in intervals:
            home = await session.get(Home, interval.home_id)
            if home is None:
                interval.quality_status = "FINALIZED"
                continue

            from src.modules.community.models import CommunityNode, EnergyCommunity

            node = (
                await session.exec(
                    select(CommunityNode).where(
                        CommunityNode.home_id == interval.home_id,
                        CommunityNode.authorized.is_(True),
                    )
                )
            ).first()
            if node is None:
                interval.quality_status = "REJECTED"
                continue
            community = await session.get(EnergyCommunity, node.community_id)
            if interval.eligible_export_wh > 0:
                existing = await session.exec(
                    select(EnergyCredit).where(
                        EnergyCredit.interval_id == interval.id,
                        EnergyCredit.owner_id == home.owner_id,
                    )
                )
                if existing.first() is None:
                    amount_sun = (
                        Decimal(interval.eligible_export_wh)
                        / Decimal(1000)
                        * community.sun_per_kwh
                    )
                    if amount_sun > 0:
                        session.add(
                            EnergyCredit(
                                interval_id=interval.id,
                                owner_id=home.owner_id,
                                energy_wh=interval.eligible_export_wh,
                                token_amount=amount_sun,
                                status="PENDING",
                            )
                        )
                        created += 1
            interval.quality_status = "FINALIZED"
            from src.modules.community.service import CommunityService

            if interval.eligible_export_wh:
                CommunityService().ledger(
                    session,
                    node.community_id,
                    "VERIFIED_INJECTION",
                    interval.id,
                    interval.eligible_export_wh,
                )
            if interval.grid_import_wh:
                CommunityService().ledger(
                    session,
                    node.community_id,
                    "VERIFIED_WITHDRAWAL",
                    interval.id,
                    interval.grid_import_wh,
                )

        await session.commit()
        return created
