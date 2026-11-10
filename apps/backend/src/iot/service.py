"""Owned-device observability from durable assessments and accepted telemetry."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlmodel import select

from src.modules.device.models import TelemetryAssessment, TelemetryMessage
from src.modules.device.service import DeviceService
from src.modules.energy.models import EnergyInterval


class TelemetryHealthService:
    async def health(self, session, user, device_id):
        device = await DeviceService().get_device_by_id(user, device_id, session)
        if not device:
            raise LookupError("Device not found")
        scope = (TelemetryAssessment.device_id == device.id) | (
            (TelemetryAssessment.device_id.is_(None))
            & (TelemetryAssessment.claimed_device_id == str(device.device_id))
        )
        counts = (
            await session.exec(
                select(
                    TelemetryAssessment.state, func.sum(TelemetryAssessment.occurrences)
                )
                .where(scope)
                .group_by(TelemetryAssessment.state)
            )
        ).all()
        last = (
            await session.exec(
                select(TelemetryMessage)
                .where(TelemetryMessage.device_id == device.id)
                .order_by(TelemetryMessage.received_at.desc())
                .limit(1)
            )
        ).first()
        intervals = (
            await session.exec(
                select(EnergyInterval)
                .where(EnergyInterval.home_id == device.home_id)
                .order_by(EnergyInterval.interval_start.desc())
                .limit(10)
            )
        ).all()
        return {
            "device_id": device.id,
            "public_device_id": device.device_id,
            "source": device.telemetry_source,
            "device_status": device.status,
            "online": device.last_seen_at is not None
            and device.last_seen_at >= datetime.now(UTC) - timedelta(minutes=5)
            and last is not None
            and last.measured_at >= datetime.now(UTC) - timedelta(minutes=5),
            "last_authenticated_telemetry": device.last_seen_at,
            "quality_counts": dict(counts),
            "last_quality": last.quality_status if last else None,
            "last_measurement_at": last.measured_at if last else None,
            "latency_seconds": str(
                max(0, (last.received_at - last.measured_at).total_seconds())
            )
            if last
            else None,
            "intervals": [
                {
                    "id": i.id,
                    "start": i.interval_start,
                    "end": i.interval_end,
                    "quality": i.quality_status,
                    "eligible_export_wh": i.eligible_export_wh,
                    "settlement_input_ready": i.quality_status == "FINALIZED",
                }
                for i in intervals
            ],
            "issuance_requires_finalized_governance_batch": True,
        }

    async def evidence(self, session, user, device_id, limit, offset):
        device = await DeviceService().get_device_by_id(user, device_id, session)
        if not device:
            raise LookupError("Device not found")
        return (
            await session.exec(
                select(TelemetryAssessment)
                .where(
                    (TelemetryAssessment.device_id == device.id)
                    | (
                        (TelemetryAssessment.device_id.is_(None))
                        & (
                            TelemetryAssessment.claimed_device_id
                            == str(device.device_id)
                        )
                    )
                )
                .order_by(TelemetryAssessment.last_seen.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
