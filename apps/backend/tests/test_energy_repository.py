"""Energy summary totals and filtering against the local PostgreSQL schema."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event

from src.core.db import AsyncSessionFactory
from src.modules.auth.models import User
from src.modules.energy.models import EnergyCredit, EnergyInterval
from src.modules.energy.repository import EnergyRepository
from src.modules.energy.schemas import EnergyCreditReadModel, EnergyIntervalReadModel
from src.modules.energy.service import EnergyService
from src.modules.home.models import Home


@pytest.mark.asyncio
async def test_summary_aggregates_all_columns_once_and_preserves_filters(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quarter = timedelta(minutes=15)
    unique = uuid4().hex
    async with AsyncSessionFactory() as db:
        user = User(
            username=unique,
            email=f"{unique}@example.com",
            first_name="Summary",
            last_name="Test",
            password_hash="not-a-login",
        )
        db.add(user)
        await db.flush()
        homes = [
            Home(owner_id=user.uid, address="Summary test", city="Cali")
            for _ in range(2)
        ]
        db.add_all(homes)
        await db.flush()
        for home, offset, values in (
            (homes[0], 0, (100, 200, 300, 500, 400)),
            (homes[0], 1, (1, 2, 3, 5, 4)),
            (homes[0], -1, (900, 900, 900, 900, 900)),
            (homes[0], 2, (900, 900, 900, 900, 900)),
            (homes[1], 0, (900, 900, 900, 900, 900)),
        ):
            db.add(EnergyInterval(
                home_id=home.id,
                interval_start=start + offset * quarter,
                interval_end=start + (offset + 1) * quarter,
                generation_wh=values[0],
                consumption_wh=values[1],
                grid_import_wh=values[2],
                grid_export_wh=values[3],
                eligible_export_wh=values[4],
                quality_status="OPEN" if offset == 1 else "FINALIZED",
            ))
        await db.flush()
        execute = AsyncMock(wraps=db.exec)
        monkeypatch.setattr(db, "exec", execute)
        repository = EnergyRepository()
        totals = await repository.summary(
            db, homes[0].id, start, start + quarter + timedelta(minutes=7)
        )
        assert totals == {
            "generation_wh": 101,
            "consumption_wh": 202,
            "grid_import_wh": 303,
            "grid_export_wh": 505,
            "eligible_export_wh": 404,
        }
        execute.assert_awaited_once()
        execute.reset_mock()
        empty = await repository.summary(
            db, homes[0].id, start + 3 * quarter, start + 4 * quarter
        )
        assert empty == dict.fromkeys(totals, 0)
        execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_energy_reads_do_not_load_relationship_graphs():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=10)
    unique = uuid4().hex
    async with AsyncSessionFactory() as db:
        user = User(
            username=unique,
            email=f"{unique}@example.com",
            first_name="Energy",
            last_name="Read",
            password_hash="not-a-login",
        )
        db.add(user)
        await db.flush()
        home = Home(owner_id=user.uid, address="Read test", city="Cali")
        db.add(home)
        await db.flush()
        interval = EnergyInterval(
            home_id=home.id, interval_start=start,
            interval_end=start + timedelta(minutes=15),
            generation_wh=100, eligible_export_wh=25, grid_export_wh=25,
            quality_status="OPEN",
        )
        db.add(interval)
        await db.flush()
        credit = EnergyCredit(
            owner_id=user.uid, interval_id=interval.id,
            energy_wh=25, token_amount=Decimal("0.025"),
        )
        db.add(credit)
        await db.flush()
        actor = SimpleNamespace(uid=user.uid, role=user.role)
        home_id, interval_id, credit_id = home.id, interval.id, credit.id
        db.expunge_all()
        reads = []

        def record_read(state):
            if state.is_select:
                reads.append(state.is_relationship_load)

        event.listen(db.sync_session, "do_orm_execute", record_read)
        try:
            service = EnergyService()
            intervals = await service.list_intervals(actor, home_id, start, end, db)
            assert [row.id for row in intervals] == [interval_id]
            assert EnergyIntervalReadModel.model_validate(intervals[0]).generation_wh == 100
            credits = await service.credits(actor, db)
            assert [row.id for row in credits] == [credit_id]
            assert EnergyCreditReadModel.model_validate(credits[0]).energy_wh == 25
            db.expunge_all()
            detail = await service.credit(actor, credit_id, db)
            assert EnergyCreditReadModel.model_validate(detail).id == credit_id
            assert reads == [False, False, False, False]
            with pytest.raises(PermissionError):
                await service._ensure_home_access(
                    db, SimpleNamespace(uid=uuid4(), role="user"), home_id
                )
            with pytest.raises(LookupError):
                await service._ensure_home_access(db, actor, uuid4())
        finally:
            event.remove(db.sync_session, "do_orm_execute", record_read)
