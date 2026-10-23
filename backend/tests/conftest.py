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

# The auth suite exercises login. A developer's AUTH_ENABLED=false (shell or
# backend/.env) turned every one of those tests into an error.
os.environ["AUTH_ENABLED"] = "true"

import pytest  # noqa: E402
from typing import AsyncGenerator, Optional  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.main import app  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.core.config import settings  # noqa: E402

# Base.metadata has to know the operator credential table before create_all
# runs, or first-run setup has nowhere to write the password.
from app.models import auth as _operator_credential_model  # noqa: E402,F401

# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"


# ---------------------------------------------------------------------------
# Operator authentication
# ---------------------------------------------------------------------------
#
# The suite drives the real login path rather than switching authentication off,
# so the gate the venue depends on is exercised by every request the tests make.
# Everything the rest of the suite needs to know about the shape of the auth API
# lives in this block.

OPERATOR_PASSWORD = "conftest-operator-passphrase-4417"

AUTH_STATUS_URL = "/api/auth/status"
AUTH_SETUP_URL = "/api/auth/setup"
AUTH_LOGIN_URL = "/api/auth/login"

# The token travels as a bearer header on HTTP and as a query parameter on the
# WebSocket channels, which cannot carry headers from a browser.
WS_TOKEN_PARAM = "token"


def bearer_headers(token: str) -> dict:
    """Authorization header carrying an operator session token."""
    return {"Authorization": f"Bearer {token}"}


def setup_payload(setup_code: str, password: str = OPERATOR_PASSWORD) -> dict:
    return {"setup_code": setup_code, "password": password}


def login_payload(password: str = OPERATOR_PASSWORD) -> dict:
    return {"password": password}


def token_from_response(payload: dict) -> Optional[str]:
    """Pull the session token out of a login or setup response body."""
    if not isinstance(payload, dict):
        return None
    for key in ("token", "access_token"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def read_setup_code() -> Optional[str]:
    """The one-time first-run code, read from wherever the app publishes it.

    It is deliberately not exposed over HTTP (contract §4), so the only honest
    way for a test to complete real setup is to read the value the process
    generated for itself.
    """
    from app.api.endpoints import auth as auth_module

    code = auth_module.get_setup_code()
    if code:
        return code
    return auth_module.ensure_setup_code()


async def provision_operator(
    ac: AsyncClient, password: str = OPERATOR_PASSWORD
) -> str:
    """Complete first-run setup if needed, then log in. Returns a session token.

    There is no path through here that yields an unauthenticated client: a suite
    that quietly stopped authenticating would prove nothing about the gate.
    """
    status = await ac.get(AUTH_STATUS_URL)
    assert status.status_code == 200, (
        f"{AUTH_STATUS_URL} must answer unauthenticated: "
        f"{status.status_code} {status.text[:200]}"
    )

    if not status.json().get("configured"):
        code = read_setup_code()
        assert code, (
            "no first-run setup code is reachable from the test process; "
            "the fixture cannot complete real setup without it"
        )
        created = await ac.post(AUTH_SETUP_URL, json=setup_payload(code, password))
        assert created.status_code in (200, 201), (
            f"first-run setup failed: {created.status_code} {created.text[:200]}"
        )
        token = token_from_response(created.json())
        if token:
            return token

    logged_in = await ac.post(AUTH_LOGIN_URL, json=login_payload(password))
    assert logged_in.status_code == 200, (
        f"operator login failed: {logged_in.status_code} {logged_in.text[:200]}"
    )
    token = token_from_response(logged_in.json())
    assert token, f"login returned no token: {logged_in.text[:200]}"
    return token


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


@pytest.fixture(scope="session")
async def operator_token(test_engine) -> str:
    """Set the operator password once per run and hold the session token.

    Session scoped on purpose: login is rate limited per client IP, and every
    test in the suite shares one IP under ASGITransport. Logging in per test
    would lock the suite out of itself.
    """
    async_session = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with async_session() as session:
            yield session

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            return await provision_operator(ac)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.fixture
async def client(db_session, operator_token) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client carrying a real operator session."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=bearer_headers(operator_token),
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def unauthenticated_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Client with no operator session, for testing the gate itself."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def lifespan_client(operator_token):
    """Client that runs the real startup/shutdown sequence.

    /health reports live subsystem state, so it only reads healthy once startup has
    actually constructed the audio analyzer and effects engine.
    """
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        test_client.headers.update(bearer_headers(operator_token))
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
