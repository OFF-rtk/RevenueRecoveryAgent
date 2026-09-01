"""
core/db.py
──────────
Async SQLAlchemy engine + session factory backed by asyncpg.

Phase 0: connection test only (SELECT 1).
Phase 1: schema migrations and model definitions will be added here.

Usage:
    from core.db import init_db, get_db

    # In FastAPI lifespan:
    await init_db(settings.database_url)

    # As a route dependency:
    async def my_route(db: AsyncSession = Depends(get_db)): ...
"""
from typing import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

log = structlog.get_logger()

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    """
    Initialise the engine and verify connectivity.
    Raises on failure so the app never silently starts with a broken DB.
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,  # validate connections before handing them out
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    # Connectivity smoke test — fail loudly if Postgres is unreachable
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        # Log only the host+db portion — never log credentials
        safe_url = database_url.split("@")[-1] if "@" in database_url else database_url
        log.info("db_connected", host=safe_url)
    except Exception as exc:
        log.error("db_connection_failed", error=str(exc), error_type=type(exc).__name__)
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields one AsyncSession per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    async with _session_factory() as session:
        yield session


# Alias used by routers — keeps import names consistent with Phase 1+ conventions
get_session = get_db


def async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory directly (for use in tests and scripts)."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _session_factory
