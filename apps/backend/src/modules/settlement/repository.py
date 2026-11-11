"""PostgreSQL concurrency boundaries and native settlement persistence."""

from uuid import UUID

from sqlalchemy import text
from sqlmodel import select
from src.modules.energy.models import OutboxEvent
from src.modules.settlement.engine import hashed
from src.modules.settlement.models import SettlementBatch


class SettlementRepository:
    async def lock(self, session, scope):
        lock = int.from_bytes(bytes.fromhex(hashed(scope)[2:])[:8], "big", signed=True)
        await session.exec(
            text("SELECT pg_advisory_xact_lock(:key)"), params={"key": lock}
        )

    async def interval(self, session, community, start, end):
        return (
            await session.exec(
                select(SettlementBatch).where(
                    SettlementBatch.community_id == community,
                    SettlementBatch.interval_start == start,
                    SettlementBatch.interval_end == end,
                )
            )
        ).first()

    async def enqueue(
        self, session, action: str, batch: SettlementBatch, entity: UUID | None = None
    ):
        entity = entity or batch.id
        # Job identity is scoped by action and immutable domain entity, not attempts.
        await self.lock(session, f"native:{action}:{entity}")
        existing = (
            await session.exec(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == f"native.{action}",
                    OutboxEvent.aggregate_id == entity,
                )
            )
        ).first()
        if existing:
            return existing
        job = OutboxEvent(
            event_type=f"native.{action}",
            aggregate_type="NATIVE_SETTLEMENT",
            aggregate_id=entity,
            payload={
                "community_id": str(batch.community_id),
                "batch_id": str(batch.id),
            },
        )
        session.add(job)
        return job
