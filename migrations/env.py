"""
Alembic migration environment — async-aware.

Reads DATABASE_URL from core.config.settings so there is one source of truth
for the connection string (the .env file). Never hard-codes credentials here.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ── Alembic config object ────────────────────────────────────────────────────
config = context.config

# Configure Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We don't use SQLAlchemy model metadata for autogenerate — migrations are
# written as explicit SQL in each version file. Set to None intentionally.
target_metadata = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_url() -> str:
    """Return the database URL from application config (reads .env)."""
    from core.config import settings  # imported lazily to avoid circular imports
    return settings.database_url


def do_run_migrations(connection) -> None:  # noqa: ANN001
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


# ── Offline mode ─────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations without a live connection — prints SQL to stdout.
    Useful for generating SQL scripts to review before applying.
    """
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ──────────────────────────────────────────────────────────────

async def run_migrations_online() -> None:
    """Run migrations against the live database via an async engine."""
    connectable = create_async_engine(_get_url(), echo=False)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ── Entry point ──────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
