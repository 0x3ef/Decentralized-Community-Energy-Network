"""Database queries for energy intervals, credits and outbox events."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.modules.energy.models import EnergyCredit, EnergyInterval, OutboxEvent


class EnergyRepository:
    """Keep SQL queries out of the energy business service."""

    async def list_intervals(
        self, session: AsyncSession, home_id: UUID,
        start: datetime, end: datetime,
    ) -> list[EnergyInterval]:
        result = await session.exec(
            select(EnergyInterval)
            .where(
                EnergyInterval.home_id == home_id,
                EnergyInterval.interval_start >= start,
                EnergyInterval.interval_end <= end,
            )
            .order_by(EnergyInterval.interval_start)
        )
        return list(result.all())

    async def summary(
        self, session: AsyncSession, home_id: UUID,
        start: datetime, end: datetime,
    ) -> dict:
        columns = (
            EnergyInterval.generation_wh,
            EnergyInterval.consumption_wh,
            EnergyInterval.grid_import_wh,
            EnergyInterval.grid_export_wh,
            EnergyInterval.eligible_export_wh,
        )
        values = []
        for column in columns:
            value = await session.exec(
                select(func.coalesce(func.sum(column), 0)).where(
                    EnergyInterval.home_id == home_id,
                    EnergyInterval.interval_start >= start,
                    EnergyInterval.interval_end <= end,
                )
            )
            values.append(int(value.one()))
        return dict(zip(
            ("generation_wh", "consumption_wh", "grid_import_wh",
             "grid_export_wh", "eligible_export_wh"),
            values,
        ))

    async def list_credits(
        self, session: AsyncSession, owner_id: UUID
    ) -> list[EnergyCredit]:
        result = await session.exec(
            select(EnergyCredit)
            .where(EnergyCredit.owner_id == owner_id)
            .order_by(EnergyCredit.created_at.desc())
        )
        return list(result.all())

    async def get_credit(
        self, session: AsyncSession, credit_id: UUID
    ) -> EnergyCredit | None:
        return await session.get(EnergyCredit, credit_id)

    async def approve_credit(
        self, session: AsyncSession, credit: EnergyCredit
    ) -> None:
        """Approve a credit and enqueue issuance in the same DB transaction."""
        if credit.status != "PENDING":
            raise ValueError("Only PENDING credits can be approved")

        existing = await session.exec(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "credit.issue",
                OutboxEvent.aggregate_id == credit.id,
                OutboxEvent.status.in_(("PENDING", "PROCESSING", "PROCESSED")),
            )
        )
        if existing.first() is None:
            session.add(
                OutboxEvent(
                    event_type="credit.issue",
                    aggregate_type="ENERGY_CREDIT",
                    aggregate_id=credit.id,
                    payload={"credit_id": str(credit.id)},
                    status="PENDING",
                    attempts=0,
                    available_at=datetime.now(timezone.utc),
                )
            )
        credit.status = "APPROVED"
