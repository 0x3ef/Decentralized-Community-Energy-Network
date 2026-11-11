"""Async database configuration shared by the API and background workers."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.config import Config
from src.core.models import register_models

register_models()

async_engine = create_async_engine(
    Config.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
# Backwards-compatible name used by older modules.
async_session_factory = AsyncSessionFactory


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory."""
    return AsyncSessionFactory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield one request-scoped database session."""
    async with AsyncSessionFactory() as session:
        yield session


async def dispose_engine() -> None:
    """Close all pooled database connections."""
    await async_engine.dispose()


async def initdb() -> None:
    """Create registered tables for local development only.

    Production schema changes must be applied through Alembic migrations.
    """
    # Import table modules so SQLModel metadata is fully populated.
    import src.modules.auth.models  # noqa: F401
    import src.modules.home.models  # noqa: F401
    import src.modules.device.models  # noqa: F401
    import src.modules.energy.models  # noqa: F401
    import src.modules.wallet.models  # noqa: F401
    import src.modules.community.models  # noqa: F401
    import src.modules.settlement.models  # noqa: F401

    async with async_engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
