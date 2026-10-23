"""
Database Configuration
======================

SQLAlchemy database setup and session management.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.core.config import settings

# SQLite will not create the folder its file lives in.
if settings.DATABASE_URL.startswith("sqlite:///"):
    _db_file = settings.DATABASE_URL.split("///", 1)[1]
    if _db_file and _db_file != ":memory:":
        Path(_db_file).parent.mkdir(parents=True, exist_ok=True)

# Handle different database backends
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite - use aiosqlite for async
    ASYNC_DATABASE_URL = settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
else:
    # PostgreSQL - use asyncpg for async
    ASYNC_DATABASE_URL = settings.DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    )

# Sync engine for Alembic migrations
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

# Async engine for application use
if settings.DATABASE_URL.startswith("sqlite"):
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db():
    """Dependency for getting sync database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
