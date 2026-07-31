"""
Phase 0 End-to-End Smoke Test
=============================

Boots the real application against a throwaway SQLite database and walks the
operator setup path: health check, fixture library population, wizard rig
creation, and DMX patch conflict detection.
"""

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select

from app.db.database import AsyncSessionLocal, Base, async_engine
from app.models.rig import Rig, RigFixture
from app.main import app

from tests.conftest import bearer_headers, provision_operator

HEALTH_READY_TIMEOUT = 15.0


@pytest.fixture
async def smoke_client() -> AsyncGenerator[AsyncClient, None]:
    """Boot the full application against an empty throwaway schema."""
    database = async_engine.url.database or ""
    assert "lighting_dev" not in database, (
        f"smoke tests must not touch the development database: {async_engine.url}"
    )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # ASGITransport does not emit lifespan events, so startup/shutdown is driven here.
    async with app.router.lifespan_context(app):
        # Unhandled endpoint exceptions must surface as 5xx responses, not as raised
        # exceptions, so the status codes themselves can be asserted on.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _wait_until_ready(client)
            # Dropping the schema took the operator credential with it, so this
            # box is at first run again and the journey below is the real one:
            # set a password, then drive every call holding the session.
            client.headers.update(bearer_headers(await provision_operator(client)))
            yield client

    # The engine is shared with the rest of the suite, whose session-scoped
    # fixture only runs create_all once - hand the schema back intact.
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _wait_until_ready(client: AsyncClient) -> Response:
    """Poll /health until the background service loops report themselves up."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + HEALTH_READY_TIMEOUT
    response = await client.get("/health")
    while response.status_code != 200 and loop.time() < deadline:
        await asyncio.sleep(0.1)
        response = await client.get("/health")
    return response


def _first_fixture_with_mode(listing: Response) -> Optional[Dict[str, Any]]:
    """Pick a library fixture that has at least one patchable mode."""
    if listing.status_code != 200:
        return None
    for item in listing.json().get("items", []):
        if item.get("modes"):
            return item
    return None


def _placements(fixture: Optional[Dict[str, Any]], count: int = 3) -> List[Dict[str, Any]]:
    """Build wizard placements spaced so no two fixtures share DMX channels."""
    if not fixture:
        return []

    mode = fixture["modes"][0]
    channel_count = mode["channel_count"]
    return [
        {
            "fixture_id": fixture["id"],
            "mode_id": mode["id"],
            "name": f"Smoke Mover {i + 1}",
            "universe": 0,
            "dmx_address": 1 + i * channel_count,
            "position_x": -3.0 + 3.0 * i,
            "position_y": 4.0,
            "position_z": 2.0,
            "group_name": "smoke",
        }
        for i in range(count)
    ]


def _wizard_payload(placements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wizard create-rig request body."""
    return {
        "rig_name": "Phase 0 Smoke Rig",
        "venue": "Smoke Venue",
        "stage_width": 10.0,
        "stage_depth": 8.0,
        "stage_height": 6.0,
        "placements": placements,
    }


async def _populate_library(client: AsyncClient) -> Dict[str, Any]:
    """Sync the bundled fixture library and return a fixture with a mode."""
    sync = await client.post("/api/fixtures/library/sync")
    assert sync.status_code == 200, (
        f"POST /api/fixtures/library/sync -> {sync.status_code}: {sync.text}"
    )

    listing = await client.get("/api/fixtures/", params={"size": 100})
    assert listing.status_code == 200, (
        f"GET /api/fixtures/ -> {listing.status_code}: {listing.text}"
    )

    fixture = _first_fixture_with_mode(listing)
    assert fixture is not None, (
        "fixture library holds no fixture with a mode after sync: "
        f"{listing.json().get('total')} fixtures returned"
    )
    return fixture


async def _create_rig_via_wizard(client: AsyncClient) -> Tuple[int, List[Dict[str, Any]]]:
    """Run the wizard create-rig flow and return the rig id and its placements."""
    fixture = await _populate_library(client)
    placements = _placements(fixture)

    response = await client.post("/api/wizard/create-rig", json=_wizard_payload(placements))
    assert response.status_code == 200, (
        f"POST /api/wizard/create-rig -> {response.status_code}: {response.text}"
    )

    rig_id = response.json().get("id")
    assert rig_id is not None, f"wizard returned a null rig id: {response.text}"
    return rig_id, placements


async def test_app_boots_and_health_is_ok(smoke_client: AsyncClient):
    """The application starts up and reports healthy."""
    response = await smoke_client.get("/health")

    assert response.status_code == 200, (
        f"GET /health -> {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["status"] == "healthy", body


async def test_fixture_library_populates_and_lists(smoke_client: AsyncClient):
    """Bundled fixtures land in the library and come back out of the list endpoint."""
    sync = await smoke_client.post("/api/fixtures/library/sync")
    assert sync.status_code == 200, (
        f"POST /api/fixtures/library/sync -> {sync.status_code}: {sync.text}"
    )

    listing = await smoke_client.get("/api/fixtures/", params={"size": 100})
    assert listing.status_code == 200, (
        f"GET /api/fixtures/ -> {listing.status_code}: {listing.text}"
    )

    data = listing.json()
    assert data["total"] > 0, data
    assert data["items"], data
    assert any(item["modes"] for item in data["items"]), (
        "no listed fixture exposes its modes"
    )
    assert any(
        mode["channels"] for item in data["items"] for mode in item["modes"]
    ), "no listed fixture mode exposes its channels"
    assert all(item["id"] is not None for item in data["items"]), data["items"]


async def test_wizard_create_rig_persists_fixtures(smoke_client: AsyncClient):
    """Wizard-created rig fixtures survive the request with a correct rig_id."""
    rig_id, placements = await _create_rig_via_wizard(smoke_client)

    async with AsyncSessionLocal() as session:
        rig = (
            await session.execute(select(Rig).where(Rig.id == rig_id))
        ).scalar_one_or_none()
        rig_fixtures = (await session.execute(select(RigFixture))).scalars().all()

    assert rig is not None, f"rig {rig_id} was not persisted"
    assert len(rig_fixtures) == len(placements), (
        f"expected {len(placements)} persisted rig fixtures, found {len(rig_fixtures)}"
    )
    assert all(rf.rig_id == rig_id for rf in rig_fixtures), (
        f"rig fixtures carry the wrong rig_id: {[rf.rig_id for rf in rig_fixtures]}"
    )
    assert sorted(rf.dmx_address for rf in rig_fixtures) == sorted(
        p["dmx_address"] for p in placements
    )
    assert all(rf.mode_id is not None for rf in rig_fixtures), (
        f"rig fixtures lost their mode: {[rf.mode_id for rf in rig_fixtures]}"
    )


async def test_rig_patch_conflicts_endpoint_responds(smoke_client: AsyncClient):
    """Patch conflict detection answers for a freshly created rig."""
    rig_id, placements = await _create_rig_via_wizard(smoke_client)

    response = await smoke_client.get(f"/api/rigs/{rig_id}/patch-conflicts")

    assert response.status_code == 200, (
        f"GET /api/rigs/{rig_id}/patch-conflicts -> {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["rig_id"] == rig_id, body
    assert body["conflict_count"] == 0, (
        f"non-overlapping placements reported conflicts: {body['conflicts']}"
    )


async def test_setup_journey_has_no_server_errors(smoke_client: AsyncClient):
    """No endpoint on the operator setup path answers with a 5xx."""
    calls: List[Tuple[str, Response]] = []

    async def record(label: str, response: Response) -> Response:
        calls.append((label, response))
        return response

    await record("GET /health", await smoke_client.get("/health"))
    await record(
        "POST /api/fixtures/library/sync",
        await smoke_client.post("/api/fixtures/library/sync"),
    )
    listing = await record(
        "GET /api/fixtures/",
        await smoke_client.get("/api/fixtures/", params={"size": 100}),
    )

    placements = _placements(_first_fixture_with_mode(listing))
    await record(
        "GET /api/wizard/venue-presets",
        await smoke_client.get("/api/wizard/venue-presets"),
    )
    create = await record(
        "POST /api/wizard/create-rig",
        await smoke_client.post("/api/wizard/create-rig", json=_wizard_payload(placements)),
    )

    rig_id = create.json().get("id") if create.status_code == 200 else 1
    await record("GET /api/rigs/", await smoke_client.get("/api/rigs/"))
    await record(f"GET /api/rigs/{rig_id}", await smoke_client.get(f"/api/rigs/{rig_id}"))
    await record(
        f"GET /api/rigs/{rig_id}/fixtures",
        await smoke_client.get(f"/api/rigs/{rig_id}/fixtures"),
    )
    await record(
        f"GET /api/rigs/{rig_id}/patch-conflicts",
        await smoke_client.get(f"/api/rigs/{rig_id}/patch-conflicts"),
    )
    await record(
        f"GET /api/rigs/{rig_id}/next-address",
        await smoke_client.get(f"/api/rigs/{rig_id}/next-address"),
    )
    await record(
        f"POST /api/rigs/{rig_id}/auto-patch",
        await smoke_client.post(f"/api/rigs/{rig_id}/auto-patch"),
    )

    # Checked first: a journey that 401s everywhere emits no 5xx either, so the
    # assertion below would hold while proving nothing.
    rejected = [
        f"{label} -> 401"
        for label, response in calls
        if response.status_code == 401
    ]
    assert not rejected, (
        "the setup journey was never authenticated:\n" + "\n".join(rejected)
    )

    server_errors = [
        f"{label} -> {response.status_code}: {response.text[:300]}"
        for label, response in calls
        if response.status_code >= 500
    ]
    assert not server_errors, "server errors on the setup path:\n" + "\n".join(server_errors)
