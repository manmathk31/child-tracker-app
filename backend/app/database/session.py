"""Async database engine and session factory."""

import logging
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger("childtrack.database")

# Global engine and session factory instances
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Obtain or initialize the application's async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if settings.is_sqlite:
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG and not settings.is_production,
            connect_args=connect_args,
            pool_pre_ping=True,
        )

        # Enforce foreign key constraints on SQLite connections
        if settings.is_sqlite:
            @event.listens_for(_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore
                try:
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()
                except Exception as exc:
                    logger.warning("Could not set SQLite foreign_keys PRAGMA: %s", exc)

        logger.info("Async database engine initialized with URL=%s", settings.DATABASE_URL.split("@")[-1])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Obtain or initialize the async session maker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session for FastAPI routes."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    """Verify that the database engine can execute a simple query.

    Returns:
        bool: True if connection is alive, False otherwise.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return False


async def close_db_engine() -> None:
    """Dispose of the database engine on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection engine closed.")
