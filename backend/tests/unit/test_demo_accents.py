"""The first demo must run accents (Q9)."""

from types import SimpleNamespace

import pytest

from app.api.endpoints import demo as demo_endpoints
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.lighting.pro_effects import ACCENT_OFF_POLICIES, ACCENT_OFF_VENUES


def _request(live_rig=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        live_rig=live_rig or {"id": None, "name": "demo", "demo": True, "fixtures": 0},
    )))


def _silenced_engine(**kwargs):
    return EffectsEngine(EffectsConfig(
        accessibility_mode="no_strobe",
        strobe_enabled=False,
        venue_mode="theatre",
        **kwargs,
    ))


def test_enable_first_demo_accents_lifts_no_strobe_and_theatre():
    engine = _silenced_engine()
    demo_endpoints.enable_first_demo_accents(engine)
    assert engine.config.accessibility_mode == "conservative"
    assert engine.config.accessibility_mode not in ACCENT_OFF_POLICIES
    assert engine.config.venue_mode == "club"
    assert engine.config.venue_mode not in ACCENT_OFF_VENUES
    assert engine.config.strobe_enabled is True


def test_enable_first_demo_accents_does_not_downgrade_performance():
    engine = EffectsEngine(EffectsConfig(
        accessibility_mode="performance",
        strobe_enabled=True,
        venue_mode="concert",
    ))
    demo_endpoints.enable_first_demo_accents(engine)
    assert engine.config.accessibility_mode == "performance"
    assert engine.config.venue_mode == "concert"
    assert engine.config.strobe_enabled is True


@pytest.mark.asyncio
async def test_start_demo_turns_accents_on(monkeypatch):
    engine = _silenced_engine()
    monkeypatch.setattr(demo_endpoints, "_effects_engine", engine)
    result = await demo_endpoints.start_demo(demo_endpoints.DemoStartRequest(genre="edm"))
    try:
        assert result["status"] == "started"
        assert engine.config.accessibility_mode == "conservative"
        assert engine.config.venue_mode == "club"
        assert engine.config.strobe_enabled is True
    finally:
        demo_endpoints.get_demo().stop()


@pytest.mark.asyncio
async def test_applying_a_demo_preset_turns_accents_on(monkeypatch):
    engine = _silenced_engine()
    monkeypatch.setattr(demo_endpoints, "_effects_engine", engine)
    await demo_endpoints.apply_venue_preset(demo_endpoints.DEFAULT_DEMO_PRESET, _request())
    assert engine.config.accessibility_mode == "conservative"
    assert engine.config.venue_mode == "club"
    assert engine.config.strobe_enabled is True
