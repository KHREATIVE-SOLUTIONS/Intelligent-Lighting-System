"""
Pytest Configuration and Fixtures
==================================

Shared fixtures for testing.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# The application binds its engines to settings.DATABASE_URL at import time, so the
# throwaway database has to be in the environment before any app module is imported.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="ils-tests-")
_TEST_DB_PATH = Path(_TEST_DB_DIR) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
atexit.register(shutil.rmtree, _TEST_DB_DIR, True)

# Tests that drive the real lifespan start the DMX output loop. The checked-in
# .env points ArtNet at the limited broadcast address, which would drive every
# real fixture on the operator's network for the duration of the run.
os.environ["ARTNET_IP"] = "127.0.0.1"

import pytest  # noqa: E402
from typing import AsyncGenerator  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.main import app  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.core.config import settings  # noqa: E402

# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def lifespan_client():
    """Client that runs the real startup/shutdown sequence.

    /health reports live subsystem state, so it only reads healthy once startup has
    actually constructed the audio analyzer and effects engine.
    """
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_show_data():
    """Sample show data for testing."""
    return {
        "name": "Test Show",
        "description": "A test lighting show",
        "duration": 180.0,
        "bpm": 128.0,
        "base_valence": 0.7,
        "base_arousal": 0.8,
    }


@pytest.fixture
def sample_rig_data():
    """Sample rig data for testing."""
    return {
        "name": "Test Rig",
        "description": "A test lighting rig",
        "venue": "Test Venue",
        "stage_width": 12.0,
        "stage_depth": 10.0,
        "stage_height": 8.0,
        "universes": [
            {
                "universe": 0,
                "protocol": "artnet",
                "ip_address": "192.168.1.100",
                "port": 6454
            }
        ],
    }


@pytest.fixture
def sample_fixture_data():
    """Sample fixture data for testing."""
    return {
        "manufacturer": "Test Manufacturer",
        "model": "Test Moving Head",
        "fixture_type": "moving_head",
        "weight": 15.5,
        "power": 450.0,
        "beam_angle": 15.0,
        "pan_range": 540.0,
        "tilt_range": 270.0,
        "has_rgb": True,
        "has_cmy": False,
        "has_color_wheel": True,
        "modes": [
            {
                "name": "Standard",
                "channel_count": 16,
                "channels": [
                    {"channel_number": 1, "channel_type": "pan", "name": "Pan"},
                    {"channel_number": 2, "channel_type": "pan_fine", "name": "Pan Fine"},
                    {"channel_number": 3, "channel_type": "tilt", "name": "Tilt"},
                    {"channel_number": 4, "channel_type": "tilt_fine", "name": "Tilt Fine"},
                    {"channel_number": 5, "channel_type": "dimmer", "name": "Dimmer"},
                    {"channel_number": 6, "channel_type": "red", "name": "Red"},
                    {"channel_number": 7, "channel_type": "green", "name": "Green"},
                    {"channel_number": 8, "channel_type": "blue", "name": "Blue"},
                ]
            }
        ]
    }


@pytest.fixture
def sample_cue_data():
    """Sample cue data for testing."""
    return {
        "name": "Test Cue",
        "cue_type": "fade",
        "start_time": 0.0,
        "duration": 2.0,
        "fade_in": 0.5,
        "fade_out": 0.5,
        "dmx_values": {
            "1": 255,
            "2": 128,
            "3": 64,
        },
        "valence": 0.5,
        "arousal": 0.5,
    }
