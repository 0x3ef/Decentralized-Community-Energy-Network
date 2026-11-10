import os

os.environ.setdefault("JWT_SECRET", "test-only-secret-at-least-32-characters")
import pytest_asyncio
from src.core.db import dispose_engine


@pytest_asyncio.fixture(autouse=True)
async def close_database_pool():
    yield
    await dispose_engine()
