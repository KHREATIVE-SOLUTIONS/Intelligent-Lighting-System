"""
Value Ranges And Strobes Off
============================

With profile ranges the engine no longer rests a strobe channel on 0: where a
profile names 0 "closed" it rests on the profile's open value instead. That
must not weaken the owner's rule that a dedicated strobe fixture goes fully
dark while strobes are disabled. The output stage still holds every one of its
slots at zero, whatever byte the engine asks for; a par with the very same
channel layout is not a strobe fixture and keeps what the engine wrote.

Read off the packets a recorder was handed in place of a socket. No socket is
opened and no packet leaves the process.
"""

from app.services.dmx.channel_ranges import resolve_channel_ranges
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager

from tests.integration.test_strobe_fixtures_off import (  # noqa: F401 - `controller` is a fixture
    ENGINE_FPS, WIRE_FPS, _strobe_layer_off, controller, disable_strobes,
)

# 0 is "closed" here, as on several real pars: the resting value is 47.
RANGES = [
    {"name": "Closed", "min_value": 0, "max_value": 31},
    {"name": "Open", "min_value": 32, "max_value": 63},
    {"name": "Strobe slow->fast", "min_value": 64, "max_value": 95},
]
RESTING = 47

STROBE_AT, PAR_AT = 1, 11                    # 1-based DMX addresses
STROBE_DIMMER, STROBE_RATE = 0, 1            # 0-based slots
PAR_RED, PAR_STROBE = 10, 13


def _rig() -> FixtureGroupManager:
    strobe = Fixture(id="st", name="Strobe", dmx_address=STROBE_AT,
                     channels={'dimmer': 0, 'strobe': 1},
                     fixture_type="strobe", pan_range=0.0, tilt_range=0.0)
    par = Fixture(id="par", name="Par", dmx_address=PAR_AT,
                  channels={'red': 0, 'green': 1, 'blue': 2, 'strobe': 3},
                  fixture_type="par", pan_range=0.0, tilt_range=0.0)
    for fixture in (strobe, par):
        fixture.range_values = {"strobe": resolve_channel_ranges("strobe", RANGES)}
    manager = FixtureGroupManager()
    manager.add_fixtures([strobe, par])
    return manager


def _render_lit(engine: EffectsEngine) -> None:
    """Every fixture full on and not strobing, rendered and handed over. The
    state is set right before the frame, as nothing promises it survives a
    rig swap or a switch being thrown."""
    for fixture in engine.fixtures.fixtures.values():
        fixture.dimmer = 1.0
        fixture.red = fixture.green = fixture.blue = 1.0
        fixture.strobe = 0.0
    engine._emit_dmx()


async def test_strobes_off_still_zeroes_a_strobe_fixture_whose_resting_value_is_not_zero(
        controller):
    engine = EffectsEngine(EffectsConfig(
        fps=ENGINE_FPS, strobe_enabled=True, accessibility_mode="performance",
        strobe_hz_cap=18.0))
    engine.set_fixture_manager(_rig())
    engine.set_dmx_callback(controller.write_universe)
    engine.attach_output_stage(controller.output_stage)

    t = 0.0
    _render_lit(engine)
    for _ in range(WIRE_FPS):
        controller._transmit_frame(t)
        t += 1.0 / WIRE_FPS
    lit = controller.socket.frames()[-1]
    assert lit[STROBE_DIMMER] == 255
    assert lit[STROBE_RATE] == RESTING, "strobes allowed: the profile's resting value goes out"
    assert lit[PAR_RED] == 255 and lit[PAR_STROBE] == RESTING

    disable_strobes(engine, _strobe_layer_off)
    _render_lit(engine)
    asked = list(controller.get_universe(0).data)
    assert asked[STROBE_RATE] == RESTING and asked[STROBE_DIMMER] == 255, (
        "the engine never asked for a nonzero byte; this test proves nothing")

    for _ in range(WIRE_FPS):
        controller._transmit_frame(t)
        t += 1.0 / WIRE_FPS
        dark = controller.socket.frames()[-1]
        assert dark[STROBE_DIMMER] == 0 and dark[STROBE_RATE] == 0, (
            "a strobe fixture got a nonzero byte on the wire with strobes disabled")
        # Same channel, same ranges, not a strobe fixture: it goes out as written.
        assert dark[PAR_RED] == 255
        assert dark[PAR_STROBE] == RESTING
