"""
Boot Wiring Tests
=================

Proves the *running application* drives the rig patched in the database.

Every other Phase 1 test verifies a layer in isolation: the loader builds a manager, the
manager renders DMX. None of them prove that starting the app connects those layers -
which is the whole claim of the phase, and exactly what was broken before it. The engine
constructed a hardcoded demo rig and startup overwrote it with a hardcoded venue preset,
so a user's patch never reached the wire.

The app binds its engines to settings.DATABASE_URL at import time, so each scenario runs
in its own subprocess with its own database. That is also the only honest way to test
"boot": it exercises the real lifespan from a cold start rather than a patched-up
in-process approximation.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]

# The demo rig puts its first mover at address 1 on universe 0, and the demo venue preset
# also starts at address 1. Patching well clear of both means a fixture found at these
# addresses can only have come from the database.
PATCH_UNIVERSE = 3
PATCH_ADDRESS = 201
SECOND_ADDRESS = 261


DRIVER = r'''
import json, os, sys

os.environ["AUDIO_CAPTURE_AUTO_START"] = "false"
os.environ["ARTNET_IP"] = "127.0.0.1"
os.environ["DEBUG"] = "false"
sys.path.insert(0, sys.argv[1])
os.environ["DATABASE_URL"] = "sqlite:///" + sys.argv[2]
MODE = sys.argv[3]

from fastapi.testclient import TestClient
from app.main import app


def patch_rig(client, universe, address, second):
    items = client.get("/api/fixtures/", params={"size": 100}).json()["items"]
    if not items:
        raise SystemExit("startup did not seed the fixture library")
    src = next(
        (f for f in items if f.get("fixture_type") in ("moving_head", "spot", "beam")),
        items[0],
    )
    r = client.post("/api/wizard/create-rig", json={
        "rig_name": "Boot Wiring Rig " + str(address),
        "stage_width": 10.0, "stage_depth": 8.0, "stage_height": 6.0,
        "placements": [
            {"fixture_id": src["id"], "name": "Patched A", "universe": universe,
             "dmx_address": address, "position_x": -2.0, "position_y": 5.0, "position_z": -1.0},
            {"fixture_id": src["id"], "name": "Patched B", "universe": universe,
             "dmx_address": second, "position_x": 2.0, "position_y": 5.0, "position_z": -1.0},
        ],
    })
    if r.status_code not in (200, 201):
        raise SystemExit("create-rig failed: %s %s" % (r.status_code, r.text[:300]))
    rig_id = r.json()["id"]
    client.post("/api/rigs/%d/activate" % rig_id)
    return rig_id


def snapshot():
    engine = app.state.effects_engine
    if engine is None:
        return {"error": "no effects engine"}
    fixtures = list(engine.fixtures.fixtures.values())
    for f in fixtures:
        f.dimmer = 1.0
        f.red = 1.0
    frames = engine.fixtures.get_dmx_frames()
    return {
        "count": len(fixtures),
        "patch": sorted([f.universe, f.dmx_address] for f in fixtures),
        "universes": engine.fixtures.get_universes(),
        "lit": {str(u): [i + 1 for i, v in enumerate(fr) if v > 0] for u, fr in frames.items()},
    }


if MODE == "empty":
    with TestClient(app):
        print("RESULT" + json.dumps(snapshot()))

elif MODE == "patched":
    with TestClient(app) as c:
        patch_rig(c, int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]))
    with TestClient(app):
        print("RESULT" + json.dumps(snapshot()))

elif MODE == "two_rigs":
    with TestClient(app) as c:
        patch_rig(c, int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]))
        patch_rig(c, 5, 100, 140)
    with TestClient(app):
        print("RESULT" + json.dumps(snapshot()))
'''


def _run(mode, *args):
    """Boot the real app in a clean process against a fresh database."""
    tmpdir = tempfile.mkdtemp(prefix="ils-boot-")
    db_path = (Path(tmpdir) / "boot.db").as_posix()
    driver = Path(tmpdir) / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(driver), str(BACKEND_DIR), db_path, mode, *[str(a) for a in args]],
        capture_output=True, text=True, timeout=300, cwd=str(BACKEND_DIR),
    )
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    if not marker:
        pytest.fail(
            "boot driver produced no result (exit %s)\nstdout tail:\n%s\nstderr tail:\n%s"
            % (proc.returncode, proc.stdout[-1500:], proc.stderr[-2000:])
        )
    return json.loads(marker[-1][len("RESULT"):])


def test_boot_drives_the_rig_patched_in_the_database():
    """The headline Phase 1 claim: startup loads the user's rig, not a hardcoded one."""
    result = _run("patched", PATCH_UNIVERSE, PATCH_ADDRESS, SECOND_ADDRESS)

    patch = [tuple(p) for p in result["patch"]]
    assert (PATCH_UNIVERSE, PATCH_ADDRESS) in patch, (
        "boot did not load the database rig; engine is driving %s" % patch[:6]
    )
    assert (PATCH_UNIVERSE, SECOND_ADDRESS) in patch

    # The demo rig is 18 fixtures and the demo venue preset is 52. Either leaking in here
    # means the fallback ran instead of the database load.
    assert result["count"] == 2, "expected only the 2 patched fixtures, got %d" % result["count"]
    assert result["universes"] == [PATCH_UNIVERSE]


def test_boot_emits_dmx_only_inside_the_patched_footprints():
    """Output follows the patch; nothing is written at the demo rig's addresses."""
    result = _run("patched", PATCH_UNIVERSE, PATCH_ADDRESS, SECOND_ADDRESS)

    assert list(result["lit"]) == [str(PATCH_UNIVERSE)]
    lit = result["lit"][str(PATCH_UNIVERSE)]
    assert lit, "patched fixtures produced no output"

    for channel in lit:
        in_a = PATCH_ADDRESS <= channel < PATCH_ADDRESS + 40
        in_b = SECOND_ADDRESS <= channel < SECOND_ADDRESS + 40
        assert in_a or in_b, "channel %d lit outside the patched footprints" % channel

    assert 1 not in lit, "address 1 lit - the demo rig's first mover leaked through"


def test_boot_falls_back_to_a_demo_rig_when_the_database_is_empty():
    """A fresh install with no rig must still produce a show rather than a dark stage."""
    result = _run("empty")

    assert result["count"] > 0, (
        "empty database left the engine with no fixtures - a fresh install would be dark"
    )
    assert result["universes"], "fallback rig produced no universes"


def test_boot_follows_the_most_recently_activated_rig():
    """`is_active` is not unique, so the loader's tiebreak decides which rig boots."""
    result = _run("two_rigs", PATCH_UNIVERSE, PATCH_ADDRESS, SECOND_ADDRESS)

    patch = [tuple(p) for p in result["patch"]]
    assert (5, 100) in patch, "boot followed the wrong rig: %s" % patch
    assert (PATCH_UNIVERSE, PATCH_ADDRESS) not in patch
