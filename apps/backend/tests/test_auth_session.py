"""Authentication regressions without external services."""

from datetime import datetime, timezone
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from src.modules.auth import routes
from src.modules.auth.models import User
from src.modules.auth.service import UserService


@pytest.mark.asyncio
async def test_operator_can_read_own_profile():
    app = FastAPI()
    app.include_router(routes.auth_router, prefix="/auth")
    now = datetime.now(timezone.utc)
    operator = SimpleNamespace(
        uid=uuid4(), username="operator", email="operator@example.com",
        first_name="Demo", last_name="Operator", role="operator",
        created_at=now, updated_at=now,
    )
    app.dependency_overrides[get_current_user] = lambda: operator
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["uid"] == str(operator.uid)
    assert "password_hash" not in response.json()


@pytest.mark.asyncio
async def test_password_verification_does_not_block_api_event_loop(monkeypatch):
    app = FastAPI()
    app.include_router(routes.auth_router, prefix="/auth")
    app.dependency_overrides[get_session] = lambda: None
    user = SimpleNamespace(uid=uuid4(), email="user@example.com", role="user", password_hash="hash")
    monkeypatch.setattr(routes.user_service, "get_user_by_email", AsyncMock(return_value=user))
    event_loop_thread = get_ident()
    verification_threads = []

    def verify(password, password_hash):
        assert password == "password" and password_hash == "hash"
        verification_threads.append(get_ident())
        return True

    monkeypatch.setattr(routes, "verify_password", verify)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", json={"email": user.email, "password": "password"})
    assert response.status_code == 200
    assert verification_threads and verification_threads[0] != event_loop_thread


@pytest.mark.asyncio
async def test_auth_lookup_does_not_load_user_relationships():
    from sqlalchemy import create_engine, event, inspect
    from sqlalchemy.exc import InvalidRequestError
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            db.add(User(username="demo", email="user@example.com", first_name="Demo", last_name="User", password_hash="hash"))
            db.commit()
            db.expunge_all()
            queries = []
            event.listen(engine, "before_cursor_execute", lambda *args: queries.append(args[2]))

            class AuthSession:
                async def exec(self, statement):
                    return db.scalars(statement)

            user = await UserService().get_user_by_email("user@example.com", AuthSession())
            assert user.email == "user@example.com"
            assert len(queries) == 1
            assert {"home", "wallets"} <= inspect(user).unloaded
            with pytest.raises(InvalidRequestError):
                _ = user.home
    finally:
        engine.dispose()
