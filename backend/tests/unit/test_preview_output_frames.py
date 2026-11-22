"""
Frames for the 3D preview
=========================

The 3D view has to draw what the engine sends, not what the look would be at
full: a blackout or a pulled-down grand master must show. These pin the one
place the preview's frames come from to the frames `_emit_dmx` hands to the DMX
callback, and pin that asking for them writes nothing.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import dmx as dmx_endpoints
from app.api.endpoints import websocket as ws
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager

MOVER = {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 4,
         'shutter': 5, 'red': 6, 'green': 7, 'blue': 8}
PAR_NO_DIMMER = {'red': 0, 'green': 1, 'blue': 2}


class _UntouchableController:
    """Stands in for the DMX controller; any use of it fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"the preview touched the DMX controller: {name}")


@pytest.fixture
def engine():
    eng = EffectsEngine(EffectsConfig())
    manager = FixtureGroupManager()
    mover = Fixture(id="mh1", name="MH 1", dmx_address=1, channels=dict(MOVER),
                    fixture_type="mover")
    par = Fixture(id="par1", name="Par 1", dmx_address=101, universe=1,
                  channels=dict(PAR_NO_DIMMER), fixture_type="par")
    manager.add_fixtures([mover, par])
    eng.set_fixture_manager(manager)
    sent = {}
    eng.set_dmx_callback(lambda universe, frame: sent.__setitem__(universe, list(frame)))
    eng.test_sent = sent
    eng.test_fixtures = (mover, par)
    return eng


def _light(engine):
    mover, par = engine.test_fixtures
    mover.dimmer = 1.0
    mover.pan = 40.0
    mover.tilt = -20.0
    mover.red = mover.green = mover.blue = 1.0
    par.dimmer = 1.0
    par.red = 1.0


def _sent(engine):
    _light(engine)
    engine._emit_dmx()
    return {u: list(f) for u, f in engine.test_sent.items()}


def test_preview_frames_are_the_frames_the_engine_sends(engine):
    sent = _sent(engine)
    assert ws.collect_output_frames(engine) == sent
    assert set(sent) == {0, 1}, "every universe the rig occupies"
    assert sent[0][4] == 255 and sent[0][5] == 255, "dimmer full, shutter open"


def test_preview_frames_follow_the_grand_master(engine):
    engine.set_grand_master(0.5)
    sent = _sent(engine)
    frames = ws.collect_output_frames(engine)
    assert frames == sent
    assert frames[0][4] == 127
    assert frames[1][100] == 127, "a par with no dimmer carries the master in its colour"
    # The look at full is a different thing, and not what the wire carries.
    assert ws.collect_dmx_frames(engine.fixtures)[0][4] == 255


def test_preview_frames_go_dark_on_blackout_and_keep_the_heads_still(engine):
    before = _sent(engine)
    engine.blackout()
    _light(engine)  # the show keeps asking for light under the latch
    frames = ws.collect_output_frames(engine)
    assert frames[0][4] == 0 and frames[1][100] == 0
    assert frames[0][0:4] == before[0][0:4], "blackout must not move a head"
    assert ws.output_status(engine)['blackout'] is True

    engine.restore()
    assert ws.collect_output_frames(engine)[0][4] == 255
    assert ws.output_status(engine)['blackout'] is False


def test_on_wire_is_false_when_held_suspended_or_with_no_controller(engine):
    controller = object()
    live = SimpleNamespace(dmx_controller=controller, dmx_output_held=False)
    assert ws.engine_output_on_wire(live, engine) is True

    held = SimpleNamespace(dmx_controller=controller, dmx_output_held=True)
    assert ws.engine_output_on_wire(held, engine) is False, "a demo rig held off the wire"

    assert ws.engine_output_on_wire(SimpleNamespace(dmx_controller=None), engine) is False

    # The identify walkthrough takes the show off the output this way.
    engine.set_dmx_callback(None)
    assert ws.engine_output_on_wire(live, engine) is False


def test_output_status_reports_the_probe_and_survives_without_one(engine, monkeypatch):
    monkeypatch.setattr(ws, "_wire_probe", None)
    assert ws.output_status(engine) == {'master': 1.0, 'blackout': False, 'on_wire': None}

    monkeypatch.setattr(ws, "_wire_probe", lambda: True)
    engine.set_grand_master(0.25)
    assert ws.output_status(engine) == {'master': 0.25, 'blackout': False, 'on_wire': True}

    def broken():
        raise RuntimeError("no app")

    monkeypatch.setattr(ws, "_wire_probe", broken)
    assert ws.output_status(engine)['on_wire'] is None


def _client(engine, **state):
    app = FastAPI()
    app.include_router(dmx_endpoints.router, prefix="/api/dmx")
    app.state.effects_engine = engine
    for key, value in state.items():
        setattr(app.state, key, value)
    return TestClient(app)


def test_endpoint_returns_the_sent_frames_and_never_touches_the_controller(engine):
    engine.set_grand_master(0.5)
    sent = _sent(engine)
    client = _client(engine, dmx_controller=_UntouchableController(), dmx_output_held=True)

    body = client.get("/api/dmx/output-frames").json()

    assert body["frames"] == {"0": sent[0], "1": sent[1]}
    assert body["master"] == 0.5
    assert body["blackout"] is False
    assert body["on_wire"] is False, "held off the wire, and it says so"
    assert engine.test_sent == sent, "asking for the frames sent nothing"


def test_endpoint_only_answers_get(engine):
    client = _client(engine, dmx_controller=_UntouchableController(), dmx_output_held=False)
    assert client.get("/api/dmx/output-frames").json()["on_wire"] is True
    assert client.post("/api/dmx/output-frames", json={}).status_code == 405
    assert client.put("/api/dmx/output-frames", json={}).status_code == 405


def test_endpoint_with_no_engine_is_empty_not_an_error():
    client = _client(None)
    assert client.get("/api/dmx/output-frames").json() == {
        "frames": {}, "master": None, "blackout": False, "on_wire": False,
    }
