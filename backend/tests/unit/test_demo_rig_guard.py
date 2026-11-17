"""
Demo rigs and the live rig
==========================

A demo rig sits at the demo's own addresses. Applied over a rig the venue
patched, its values go to the venue's fixtures - the wire audit of 2026-11
measured 256 foreign channels on universe 0 and 200 on universe 1 from one
call. The endpoints refuse while a patched rig is live, and the visualizer is
told which demo rig the engine is actually running.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.endpoints import demo as demo_endpoints
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine


def _request(live_rig):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(live_rig=live_rig)))


@pytest.fixture
def engine(monkeypatch):
    engine = EffectsEngine(EffectsConfig())
    monkeypatch.setattr(demo_endpoints, "_effects_engine", engine)
    return engine


@pytest.mark.asyncio
async def test_a_demo_rig_is_refused_while_a_patched_rig_is_live(engine):
    before = engine.fixtures
    request = _request({"id": 3, "name": "Main Room", "demo": False, "fixtures": 16})

    with pytest.raises(HTTPException) as refused:
        await demo_endpoints.apply_venue_preset("club_night", request)

    assert refused.value.status_code == 409
    assert "Main Room" in refused.value.detail
    assert engine.fixtures is before, "the patched rig must still be the one on the engine"
    assert request.app.state.live_rig["demo"] is False


@pytest.mark.asyncio
async def test_starting_the_demo_with_a_preset_is_refused_too(engine):
    request = _request({"id": 3, "name": "Main Room", "demo": False, "fixtures": 16})
    body = demo_endpoints.DemoStartRequest(venue_preset="club_night")

    with pytest.raises(HTTPException) as refused:
        await demo_endpoints.start_demo(body, request)

    assert refused.value.status_code == 409


@pytest.mark.asyncio
async def test_a_demo_rig_replaces_another_demo_rig_and_is_recorded(engine):
    request = _request({"id": None, "name": "pro_beam_room", "demo": True, "fixtures": 52})

    result = await demo_endpoints.apply_venue_preset("club_night", request)

    assert result["fixture_count"] == 34
    assert len(engine.fixtures.fixtures) == 34
    assert request.app.state.live_rig == {"id": None, "name": "club_night", "demo": True, "fixtures": 34}


@pytest.mark.asyncio
async def test_the_visualizer_is_given_the_demo_rig_the_engine_is_running():
    running = await demo_endpoints.get_demo_rig(None, _request({"name": "club_night", "demo": True}))
    assert running["venue"] == "club_night" and len(running["fixtures"]) == 34

    # With a patched rig live, or nothing known, it is the default demo rig.
    patched = await demo_endpoints.get_demo_rig(None, _request({"name": "Main Room", "demo": False}))
    assert patched["venue"] == demo_endpoints.DEFAULT_DEMO_PRESET
    unknown = await demo_endpoints.get_demo_rig()
    assert unknown["venue"] == demo_endpoints.DEFAULT_DEMO_PRESET
