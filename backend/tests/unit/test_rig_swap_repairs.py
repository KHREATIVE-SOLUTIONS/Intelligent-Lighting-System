"""
Runtime Rig Swap
================

Switching venue is the most common runtime rig change. Anything the outgoing rig
left behind - a universe that stops being addressed, a key-light binding to a
fixture id the new rig reuses - keeps driving output nobody asked for.
"""

import pytest

from app.api.endpoints import demo as demo_endpoints
from app.services.demo.venue_presets import create_venue_rig
from app.services.effects import EffectsConfig, EffectsEngine
from app.services.lighting.key_lighting import KeyLightConfig, PerformerZone


def _run(engine, frames=10):
    for _ in range(frames):
        engine.update_audio(energy=0.7, bass=0.6, mid=0.5, high=0.4, is_beat=True, bpm=128)
        engine.update(1 / 30.0)


def _wired_engine():
    """An engine whose DMX callback latches frames the way the ArtNet path does."""
    universes = {}
    engine = EffectsEngine(EffectsConfig())
    engine.set_dmx_callback(lambda universe, frame: universes.__setitem__(universe, list(frame)))
    return engine, universes


def _lit(universes, universe):
    return sum(1 for value in universes.get(universe, []) if value)


def test_swapping_to_a_smaller_rig_blacks_out_the_universes_it_drops():
    engine, universes = _wired_engine()
    big, _ = create_venue_rig("festival_mainstage")
    engine.set_fixture_manager(big)
    _run(engine)

    assert _lit(universes, 1) > 0, "the two-universe preset should light universe 1"

    small, _ = create_venue_rig("small_nightclub")
    engine.set_fixture_manager(small)
    _run(engine)

    assert _lit(universes, 1) == 0, "universe 1 would otherwise stay latched forever"
    assert _lit(universes, 0) > 0


@pytest.mark.asyncio
async def test_the_venue_preset_endpoint_swaps_through_the_engine_setter():
    engine, universes = _wired_engine()
    demo_endpoints.set_demo_effects_engine(engine)
    try:
        await demo_endpoints.apply_venue_preset("festival_mainstage")
        _run(engine)
        assert _lit(universes, 1) > 0

        await demo_endpoints.apply_venue_preset("small_nightclub")
        _run(engine)

        assert _lit(universes, 1) == 0
    finally:
        demo_endpoints.set_demo_effects_engine(None)


def test_key_light_bindings_do_not_survive_onto_a_different_rig():
    """Two presets share fixture ids, so a stale binding silently floors fixtures
    in the new rig at the old rig's minimum intensity."""
    engine = EffectsEngine(EffectsConfig())
    old_rig, _ = create_venue_rig("festival_mainstage")
    new_rig, _ = create_venue_rig("small_nightclub")
    engine.set_fixture_manager(old_rig)

    only_in_old = sorted(set(old_rig.fixtures) - set(new_rig.fixtures))[:2]
    in_both = sorted(set(old_rig.fixtures) & set(new_rig.fixtures))[:2]
    assert only_in_old and in_both

    zone = PerformerZone.DJ_BOOTH
    engine.key_lighting.configure_zone(
        zone, KeyLightConfig(zone=zone, min_intensity=0.85, active=True)
    )
    engine.key_lighting.assign_fixtures(zone, in_both + only_in_old)
    _run(engine, frames=5)

    engine.set_fixture_manager(new_rig)

    for fixture_id in only_in_old:
        assert engine.key_lighting.get_key_light_override(
            fixture_id, 0.0, 1.0, 1.0, 1.0
        ) is None, f"{fixture_id} is not in the new rig and must not stay bound"

    for fixture_id in in_both:
        assert engine.key_lighting.get_key_light_override(
            fixture_id, 0.0, 1.0, 1.0, 1.0
        ) is not None

    # The zone itself is operator configuration and survives.
    assert zone in engine.key_lighting._configs
    assert engine.key_lighting._configs[zone].min_intensity == 0.85
    assert engine.key_lighting._configs[zone].fixture_ids == in_both


def test_the_fixture_snapshot_carries_the_universe():
    """The visualizer binds fixture state by DMX address; without a universe two
    fixtures at the same address in different universes bind to each other."""
    engine = EffectsEngine(EffectsConfig())
    manager, _ = create_venue_rig("festival_mainstage")
    engine.set_fixture_manager(manager)
    _run(engine, frames=3)

    snapshot = engine.get_fixture_state_snapshot()

    assert snapshot
    assert all('universe' in entry for entry in snapshot)
    assert {entry['universe'] for entry in snapshot} == set(manager.get_universes())
