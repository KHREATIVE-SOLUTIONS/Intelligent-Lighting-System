"""
Rig Activate, live
==================

A rig made or edited in the UI has to reach the running show when the operator
presses Activate, with no restart: the engine's fixtures, patch and universes
are replaced between two frames, the status the 3D view polls names the new
rig, the choice outlasts a restart, and a rig that could not be driven
correctly is refused while the old one stays on stage.

Nothing here opens a socket. The engine under test is a bare EffectsEngine put
on `app.state` with no DMX controller behind it; where a test needs to see
output it records what the engine hands its DMX callback. The database is the
throwaway one conftest creates, and the restart test boots the app in its own
process against its own temporary directory.
"""

import asyncio
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.rig import Rig
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.rig.rig_loader import load_active_rig

BACKEND_DIR = Path(__file__).resolve().parents[1]

STATE_KEYS = (
    "effects_engine", "fixture_manager", "live_rig", "live_rig_version", "dmx_output_held",
)
_MISSING = object()


@pytest.fixture(autouse=True)
async def engine(test_engine):
    """A show engine on the app, on its built-in demo rig, as after a fresh boot.

    `app` is shared by the whole run and activation commits, so everything this
    puts on it is taken back off, and no rig is left marked active for a later
    test's boot to pick up.
    """
    saved = {key: getattr(app.state, key, _MISSING) for key in STATE_KEYS}
    show = EffectsEngine(EffectsConfig())
    app.state.effects_engine = show
    app.state.fixture_manager = show.fixtures
    app.state.live_rig = {
        "id": None, "name": "pro_beam_room", "demo": True, "fixtures": len(show.fixtures.fixtures),
    }
    app.state.dmx_output_held = True
    try:
        yield show
    finally:
        show.running = False
        for key, value in saved.items():
            if value is _MISSING:
                if hasattr(app.state, key):
                    delattr(app.state, key)
            else:
                setattr(app.state, key, value)
        async with AsyncSession(test_engine) as session:
            await session.execute(update(Rig).values(is_active=False))
            await session.commit()


async def _profile(client: AsyncClient, sample_fixture_data, model: str):
    """A 16-channel moving head in the library. Returns (fixture id, mode id)."""
    response = await client.post("/api/fixtures/", json={**sample_fixture_data, "model": model})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["modes"][0]["id"]


async def _rig(client: AsyncClient, sample_rig_data, profile, name: str, universe: int, addresses):
    """A rig patched through the API. Returns (rig id, [rig fixture ids])."""
    fixture_id, mode_id = profile
    created = await client.post("/api/rigs/", json={**sample_rig_data, "name": name})
    assert created.status_code == 201, created.text
    rig_id = created.json()["id"]
    patched = []
    for index, address in enumerate(addresses):
        response = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
            "fixture_id": fixture_id, "mode_id": mode_id, "name": f"{name} {index + 1}",
            "universe": universe, "dmx_address": address,
        })
        assert response.status_code == 201, response.text
        patched.append(response.json()["id"])
    return rig_id, patched


def _patch(show: EffectsEngine):
    return sorted((f.universe, f.dmx_address) for f in show.fixtures.fixtures.values())


async def _status(client: AsyncClient) -> dict:
    response = await client.get("/api/effects/status")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Going live
# ---------------------------------------------------------------------------


async def test_a_rig_made_through_the_api_goes_on_the_engine_without_a_restart(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot A")
    rig_id, patched = await _rig(client, sample_rig_data, profile, "Main room", 2, [1, 17, 33])
    assert _patch(engine) != [(2, 1), (2, 17), (2, 33)], "the rig reached the engine before Activate"

    response = await client.post(f"/api/rigs/{rig_id}/activate")

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True
    assert response.json()["live"] is True
    assert _patch(engine) == [(2, 1), (2, 17), (2, 33)]
    assert sorted(engine.fixtures.fixtures) == sorted(f"rf{i}" for i in patched)
    assert engine.fixtures.get_universes() == [2]
    # The fixtures are grouped and typed for the effects that look them up.
    assert len(engine.fixtures.get_fixtures_in_group("movers")) == 3
    assert app.state.fixture_manager is engine.fixtures
    # The demo rig was kept off the wire; the venue's own patch is not.
    assert app.state.dmx_output_held is False


async def test_a_stopped_engine_takes_the_rig_and_renders_it(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Stopped")
    rig_id, _ = await _rig(client, sample_rig_data, profile, "Stopped", 6, [101, 201])
    sent = []
    engine.set_dmx_callback(lambda universe, frame: sent.append((universe, list(frame))))
    assert engine.running is False

    assert (await client.post(f"/api/rigs/{rig_id}/activate")).status_code == 200
    sent.clear()
    engine.update(1 / 40)
    engine.update(1 / 40)

    assert sent, "the engine rendered nothing for the new rig"
    assert {universe for universe, _ in sent} == {6}
    for _, frame in sent:
        outside = [i + 1 for i, v in enumerate(frame) if v and not (101 <= i + 1 <= 116 or 201 <= i + 1 <= 216)]
        assert not outside, f"channels lit outside the patched fixtures: {outside[:8]}"


async def test_status_names_the_new_live_rig_and_a_new_version(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Status")
    rig_id, _ = await _rig(client, sample_rig_data, profile, "Status room", 1, [1, 17])
    before = await _status(client)
    assert before["live_rig_demo"] is True

    activated = await client.post(f"/api/rigs/{rig_id}/activate")
    after = await _status(client)

    assert after["live_rig_id"] == rig_id
    assert after["live_rig_name"] == "Status room"
    assert after["live_rig_demo"] is False
    assert after["live_rig_fixtures"] == 2
    assert after["live_rig_version"] != before["live_rig_version"]
    assert activated.json()["live_rig_version"] == after["live_rig_version"]


async def test_reactivating_the_active_rig_applies_its_edits(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Edit")
    rig_id, patched = await _rig(client, sample_rig_data, profile, "Edited", 3, [1, 17])
    assert (await client.post(f"/api/rigs/{rig_id}/activate")).status_code == 200
    first = (await _status(client))["live_rig_version"]

    moved = await client.put(f"/api/rigs/{rig_id}/fixtures/{patched[1]}", json={"dmx_address": 200})
    assert moved.status_code == 200, moved.text
    added = await client.post(f"/api/rigs/{rig_id}/fixtures", json={
        "fixture_id": profile[0], "mode_id": profile[1], "universe": 4, "dmx_address": 50,
    })
    assert added.status_code == 201, added.text
    assert _patch(engine) == [(3, 1), (3, 17)], "an edit reached the stage before Activate"

    again = await client.post(f"/api/rigs/{rig_id}/activate")

    assert again.status_code == 200, again.text
    assert _patch(engine) == [(3, 1), (3, 200), (4, 50)]
    status = await _status(client)
    assert status["live_rig_id"] == rig_id
    assert status["live_rig_fixtures"] == 3
    assert status["live_rig_version"] != first, "the 3D view could not tell the rig was applied again"


# ---------------------------------------------------------------------------
# Refusing a rig that could not be driven correctly
# ---------------------------------------------------------------------------


async def _live_rig(client, sample_rig_data, profile, name="Good rig"):
    rig_id, _ = await _rig(client, sample_rig_data, profile, name, 1, [1, 17])
    assert (await client.post(f"/api/rigs/{rig_id}/activate")).status_code == 200
    return rig_id


async def _assert_still_on(client: AsyncClient, engine, good_id: int, manager, bad_id: int):
    assert engine.fixtures is manager, "the engine was handed another rig"
    assert _patch(engine) == [(1, 1), (1, 17)]
    status = await _status(client)
    assert status["live_rig_id"] == good_id
    assert (await client.get(f"/api/rigs/{good_id}")).json()["is_active"] is True
    assert (await client.get(f"/api/rigs/{bad_id}")).json()["is_active"] is False


async def test_a_rig_with_overlapping_addresses_is_refused_and_the_old_rig_stays_live(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Overlap")
    good_id = await _live_rig(client, sample_rig_data, profile)
    manager = engine.fixtures
    version = (await _status(client))["live_rig_version"]
    bad_id, patched = await _rig(client, sample_rig_data, profile, "Overlapping", 2, [1, 100])
    # Sixteen channels at 1 and sixteen at 10 share seven of them.
    moved = await client.put(f"/api/rigs/{bad_id}/fixtures/{patched[1]}", json={"dmx_address": 10})
    assert moved.status_code == 200, moved.text

    response = await client.post(f"/api/rigs/{bad_id}/activate")

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "overlaps" in detail and "Overlapping 2" in detail and "universe 2" in detail
    await _assert_still_on(client, engine, good_id, manager, bad_id)
    assert (await _status(client))["live_rig_version"] == version


async def test_a_rig_with_a_fixture_running_off_its_universe_is_refused(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Edge")
    good_id = await _live_rig(client, sample_rig_data, profile)
    manager = engine.fixtures
    bad_id, patched = await _rig(client, sample_rig_data, profile, "Off the end", 2, [1, 100])
    # Moving a fixture does not check its footprint, so the edit is accepted.
    moved = await client.put(f"/api/rigs/{bad_id}/fixtures/{patched[1]}", json={"dmx_address": 505})
    assert moved.status_code == 200, moved.text

    response = await client.post(f"/api/rigs/{bad_id}/activate")

    assert response.status_code == 422, response.text
    assert "past channel 512" in response.json()["detail"]
    await _assert_still_on(client, engine, good_id, manager, bad_id)


async def test_a_rig_with_an_unknown_fixture_profile_is_refused(
    client: AsyncClient, engine, db_session, sample_rig_data, sample_fixture_data
):
    from app.models.rig import RigFixture

    profile = await _profile(client, sample_fixture_data, "Activate Spot Unknown")
    good_id = await _live_rig(client, sample_rig_data, profile)
    manager = engine.fixtures
    bad_id, _ = await _rig(client, sample_rig_data, profile, "Unknown profile", 2, [1])
    # A patch whose profile is not in the library, as a deleted profile or a
    # half-finished import leaves behind.
    db_session.add(RigFixture(
        rig_id=bad_id, fixture_id=987654, name="Mystery light", universe=2, dmx_address=200,
    ))
    await db_session.flush()

    response = await client.post(f"/api/rigs/{bad_id}/activate")

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "Mystery light" in detail and "no fixture profile" in detail
    await _assert_still_on(client, engine, good_id, manager, bad_id)


async def test_an_unknown_rig_is_a_404_and_changes_nothing(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot 404")
    good_id = await _live_rig(client, sample_rig_data, profile)
    manager = engine.fixtures

    response = await client.post("/api/rigs/99999999/activate")

    assert response.status_code == 404
    assert engine.fixtures is manager
    assert (await client.get(f"/api/rigs/{good_id}")).json()["is_active"] is True


async def test_an_empty_rig_is_marked_active_but_the_show_keeps_its_rig(
    client: AsyncClient, engine, sample_rig_data
):
    manager = engine.fixtures
    created = await client.post("/api/rigs/", json={**sample_rig_data, "name": "Nothing in it"})
    rig_id = created.json()["id"]

    response = await client.post(f"/api/rigs/{rig_id}/activate")

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True
    assert response.json()["live"] is False
    assert engine.fixtures is manager, "a rig with no fixtures would run a dark show"
    assert (await _status(client))["live_rig_demo"] is True


# ---------------------------------------------------------------------------
# Swapping under a running engine
# ---------------------------------------------------------------------------


async def test_activating_while_the_engine_runs_swaps_between_frames(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data, caplog
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Running")
    old_id, _ = await _rig(client, sample_rig_data, profile, "Old", 1, [1, 17])
    new_id, _ = await _rig(client, sample_rig_data, profile, "New", 4, [300, 316])
    assert (await client.post(f"/api/rigs/{old_id}/activate")).status_code == 200

    sent = []
    engine.set_dmx_callback(lambda universe, frame: sent.append((universe, list(frame))))
    caplog.set_level(logging.ERROR)
    loop_task = asyncio.create_task(engine.run())
    try:
        await asyncio.sleep(0.15)
        assert engine.running is True
        assert {universe for universe, _ in sent} == {1}, "the old rig was not running first"

        mark = len(sent)
        response = await client.post(f"/api/rigs/{new_id}/activate")
        await asyncio.sleep(0.15)
    finally:
        engine.running = False
        await asyncio.wait_for(loop_task, 2)

    assert response.status_code == 200, response.text
    assert not [r for r in caplog.records if "EffectsEngine update error" in r.getMessage()], (
        "a frame failed around the swap"
    )
    assert _patch(engine) == [(4, 300), (4, 316)]

    after = sent[mark:]
    old_frames = [frame for universe, frame in after if universe == 1]
    new_frames = [frame for universe, frame in after if universe == 4]
    assert len(new_frames) >= 3, "the engine stopped rendering after the swap"
    # The universe the show left is blacked out once, then never written again:
    # its fixtures would otherwise hold their last values all night.
    assert old_frames and not any(old_frames[-1]), "the old universe was left lit"
    last_old = max(i for i, (universe, _) in enumerate(after) if universe == 1)
    first_new = min(i for i, (universe, _) in enumerate(after) if universe == 4)
    assert last_old < first_new, "frames for the old rig were sent after the new rig started"
    # No frame carries the old rig's patch into the new universe.
    for frame in new_frames:
        outside = [i + 1 for i, v in enumerate(frame) if v and not 300 <= i + 1 <= 331]
        assert not outside, f"channels lit outside the new rig's fixtures: {outside[:8]}"


# ---------------------------------------------------------------------------
# Outlasting a restart
# ---------------------------------------------------------------------------


async def test_a_fresh_load_picks_the_activated_rig(
    client: AsyncClient, engine, test_engine, sample_rig_data, sample_fixture_data
):
    profile = await _profile(client, sample_fixture_data, "Activate Spot Persist")
    first_id, _ = await _rig(client, sample_rig_data, profile, "First", 1, [1])
    second_id, _ = await _rig(client, sample_rig_data, profile, "Second", 2, [40, 60])
    for rig_id in (first_id, second_id, first_id, second_id):
        assert (await client.post(f"/api/rigs/{rig_id}/activate")).status_code == 200

    # What boot does: a new session, knowing nothing of this one.
    async with AsyncSession(test_engine) as fresh:
        manager, rig = await load_active_rig(fresh)
        active = (await fresh.execute(Rig.__table__.select().where(Rig.is_active == True))).all()

    assert rig is not None and rig.id == second_id
    assert sorted((f.universe, f.dmx_address) for f in manager.fixtures.values()) == [(2, 40), (2, 60)]
    assert [row.id for row in active] == [second_id], "more than one rig was left marked active"


async def test_a_rig_made_later_does_not_take_the_active_mark(
    client: AsyncClient, engine, sample_rig_data, sample_fixture_data
):
    """Every new rig used to be stamped active, so the newest one won the next restart."""
    first = await client.post("/api/rigs/", json={**sample_rig_data, "name": "First on the box"})
    assert first.json()["is_active"] is True, "a fresh install's first rig must still boot"
    profile = await _profile(client, sample_fixture_data, "Activate Spot Later")
    venue_id, _ = await _rig(client, sample_rig_data, profile, "Venue", 1, [1])
    assert (await client.post(f"/api/rigs/{venue_id}/activate")).status_code == 200

    later = await client.post("/api/rigs/", json={**sample_rig_data, "name": "Made later"})
    wizard = await client.post("/api/wizard/create-rig", json={
        "rig_name": "Wizard later", "stage_width": 10.0, "stage_depth": 8.0, "stage_height": 6.0,
        "placements": [{"fixture_id": profile[0], "universe": 9, "dmx_address": 1}],
    })
    assert wizard.status_code in (200, 201), wizard.text

    assert later.json()["is_active"] is False
    active = (await client.get("/api/rigs/", params={"active_only": True, "size": 100})).json()["items"]
    assert [rig["id"] for rig in active] == [venue_id]


RESTART_DRIVER = r'''
import json, os, sys

os.environ["AUDIO_CAPTURE_AUTO_START"] = "false"
os.environ["ARTNET_IP"] = "127.0.0.1"
os.environ["DEBUG"] = "false"
sys.path.insert(0, sys.argv[1])
os.environ["DATABASE_URL"] = "sqlite:///" + sys.argv[2]

from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints.auth import ensure_setup_code


def patch_rig(client, src, name, universe, addresses):
    rig_id = client.post("/api/rigs/", json={
        "name": name, "stage_width": 10.0, "stage_depth": 8.0, "stage_height": 6.0,
    }).json()["id"]
    ids = []
    for address in addresses:
        r = client.post("/api/rigs/%d/fixtures" % rig_id, json={
            "fixture_id": src["id"], "mode_id": src["modes"][0]["id"],
            "universe": universe, "dmx_address": address,
        })
        if r.status_code != 201:
            raise SystemExit("patch failed: %s %s" % (r.status_code, r.text[:300]))
        ids.append(r.json()["id"])
    return rig_id, ids


def stage():
    engine = app.state.effects_engine
    return {
        "patch": sorted([f.universe, f.dmx_address] for f in engine.fixtures.fixtures.values()),
        "live_rig": app.state.live_rig,
        "held": app.state.dmx_output_held,
    }


result = {}
with TestClient(app) as c:
    r = c.post("/api/auth/setup", json={
        "setup_code": ensure_setup_code(), "password": "restart-driver-passphrase",
    })
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    items = c.get("/api/fixtures/", params={"size": 100}).json()["items"]
    src = next(f for f in items if f.get("modes") and f["modes"][0]["channel_count"] >= 4)
    span = src["modes"][0]["channel_count"]

    venue, _ = patch_rig(c, src, "Venue", 3, [1, 1 + span])
    other, _ = patch_rig(c, src, "Other", 5, [101])
    broken, broken_ids = patch_rig(c, src, "Broken", 7, [1, 1 + span])
    c.put("/api/rigs/%d/fixtures/batch-update" % broken, json={
        "fixtures": [{"id": broken_ids[1], "dmx_address": 2}],
    })

    result["demo_first"] = stage()["live_rig"]["demo"]
    result["codes"] = [
        c.post("/api/rigs/%d/activate" % rig_id).status_code for rig_id in (other, venue, broken)
    ]
    result["venue_id"] = venue
    result["span"] = span
    result["before_restart"] = stage()

# A second start of the same app on the same database: a restart.
with TestClient(app):
    result["after_restart"] = stage()

print("RESULT" + json.dumps(result))
'''


def test_the_activated_rig_is_the_one_a_restart_boots_on():
    """Activation is what a restart follows; a refused rig leaves no trace of itself."""
    tmpdir = tempfile.mkdtemp(prefix="ils-activate-")
    driver = Path(tmpdir) / "driver.py"
    driver.write_text(RESTART_DRIVER, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(driver), str(BACKEND_DIR), (Path(tmpdir) / "restart.db").as_posix()],
        capture_output=True, text=True, timeout=300, cwd=str(BACKEND_DIR),
    )
    marker = [line for line in proc.stdout.splitlines() if line.startswith("RESULT")]
    if not marker:
        pytest.fail(
            "restart driver produced no result (exit %s)\nstdout tail:\n%s\nstderr tail:\n%s"
            % (proc.returncode, proc.stdout[-1500:], proc.stderr[-2000:])
        )
    result = json.loads(marker[-1][len("RESULT"):])
    expected = [[3, 1], [3, 1 + result["span"]]]

    assert result["demo_first"] is True
    assert result["codes"] == [200, 200, 422]
    for moment in ("before_restart", "after_restart"):
        assert result[moment]["patch"] == expected, f"{moment}: engine is on {result[moment]['patch']}"
        assert result[moment]["live_rig"]["id"] == result["venue_id"]
        assert result[moment]["live_rig"]["demo"] is False
        assert result[moment]["held"] is False
