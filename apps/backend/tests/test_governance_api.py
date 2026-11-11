"""Ordinary accounts can propose a boundary but cannot acquire operating roles."""

from uuid import uuid4

import pytest
from sqlmodel import select
from src.core.db import AsyncSessionFactory
from src.modules.auth.models import User
from src.modules.community.models import CommunityMembership
from src.modules.community.service import CommunityService


@pytest.mark.asyncio
async def test_proposal_never_grants_operator_authority():
    async with AsyncSessionFactory() as db:
        suffix = uuid4().hex
        user = User(
            username=suffix,
            email=suffix + "@example.com",
            first_name="Proposal",
            last_name="Test",
            password_hash="not-a-login",
        )
        db.add(user)
        await db.flush()
        community = await CommunityService().create(db, user, "Proposed boundary")
        assert community.status == "DRAFT"
        membership = (
            await db.exec(
                select(CommunityMembership).where(
                    CommunityMembership.community_id == community.id
                )
            )
        ).one()
        assert membership.role == "member" and membership.status == "PENDING"
        with pytest.raises(PermissionError, match="governance"):
            await CommunityService().membership(
                db, community.id, user.uid, operator=True
            )
        await db.rollback()
