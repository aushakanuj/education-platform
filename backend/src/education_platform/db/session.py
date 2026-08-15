from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from education_platform.core.config import get_settings
from education_platform.db.url import to_async_url

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_bound_url: str | None = None


def reset_engine() -> None:
    """Dispose cached engine so the next call picks up current settings."""
    global _engine, _session_factory, _bound_url
    if _engine is not None:
        # dispose is async; sync dispose via sync_engine for test teardown convenience
        _engine.sync_engine.dispose()
    _engine = None
    _session_factory = None
    _bound_url = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory, _bound_url
    settings = get_settings()
    database_url = to_async_url(settings.database_url)
    if _engine is None or _bound_url != database_url:
        if _engine is not None:
            _engine.sync_engine.dispose()
        _bound_url = database_url
        _engine = create_async_engine(database_url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
