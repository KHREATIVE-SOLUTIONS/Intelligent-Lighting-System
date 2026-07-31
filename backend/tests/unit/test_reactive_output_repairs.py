"""
Legacy Reactive Output Path
===========================

The music-reactive websocket path writes DMX directly rather than through the
engine's renderer, so it has to honour the same rules: a fixture with no travel
is never given movement, and a strobe is not a bright LED bar.
"""

import pytest

from app.api.endpoints.websocket import apply_reactive_lighting, _reactive_roles
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager


ANALYSIS = {
    'beat': {
        'is_beat': True, 'beat_position': 1, 'beat_count': 4, 'bpm': 128,
        'bar_count': 2, 'is_bar': True, 'is_phrase': True, 'is_section': True,
    },
    'mood': {'valence': 0.7, 'arousal': 0.9},
    'frequency': {
        'rms_energy': 0.6, 'spectral_flux': 0.05,
        'bands': [
            {'name': 'bass', 'energy': 0.7},
            {'name': 'mid', 'energy': 0.5},
            {'name': 'high', 'energy': 0.4},
        ],
    },
    'ml': {'structure': {'section': 'chorus'}},
}

IDLE = {
    **ANALYSIS,
    'mood': {'valence': 0.5, 'arousal': 0.2},
    'beat': {**ANALYSIS['beat'], 'is_section': False, 'is_phrase': False, 'is_bar': False},
}


class _Controller:
    def __init__(self):
        self.writes = []

    async def set_channel(self, universe, address, value):
        self.writes.append((universe, address, value))

    def for_fixture(self, fixture, span):
        low = fixture.dmx_address
        return [w for w in self.writes if low <= w[1] < low + span]


def _rig():
    par = Fixture(
        id="par", name="Static Par", dmx_address=1,
        channels={'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
                  'dimmer': 5, 'red': 7, 'green': 8, 'blue': 9},
        fixture_type="wash", pan_range=0.0, tilt_range=0.0, x=-2.0,
    )
    mover = Fixture(
        id="mh", name="MH", dmx_address=100,
        channels={'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3, 'dimmer': 5},
        fixture_type="mover", x=0.0,
    )
    strobe = Fixture(
        id="strobe", name="Strobe", dmx_address=300,
        channels={'dimmer': 0, 'strobe': 1, 'other': 2, 'speed': 3},
        fixture_type="strobe", pan_range=0.0, tilt_range=0.0, x=2.0,
    )
    manager = FixtureGroupManager()
    manager.add_fixtures([par, mover, strobe])
    return manager, par, mover, strobe


def test_a_strobe_gets_its_own_role():
    manager, par, mover, strobe = _rig()

    roles = _reactive_roles(manager)

    assert [f.id for f in roles['strobes']] == ["strobe"]
    assert [f.id for f in roles['movers']] == ["mh"]
    assert [f.id for f in roles['washes']] == ["par"]
    assert roles['bars'] == []


@pytest.mark.asyncio
async def test_a_static_fixture_is_never_given_pan_or_tilt():
    manager, par, mover, strobe = _rig()
    controller = _Controller()

    await apply_reactive_lighting(controller, ANALYSIS, fixtures=manager)

    par_writes = controller.for_fixture(par, 10)
    assert par_writes, "the par should still be driven"
    assert all(write[1] not in (1, 2, 3, 4) for write in par_writes), par_writes
    assert any(write[1] == 6 for write in par_writes), "dimmer still reaches it"

    mover_writes = controller.for_fixture(mover, 6)
    assert any(write[1] == 100 for write in mover_writes), "a real mover still pans"


@pytest.mark.asyncio
async def test_a_strobe_idles_dark():
    manager, par, mover, strobe = _rig()
    controller = _Controller()

    await apply_reactive_lighting(controller, IDLE, fixtures=manager)

    strobe_writes = controller.for_fixture(strobe, 4)
    assert strobe_writes
    assert all(write[2] == 0 for write in strobe_writes), strobe_writes


@pytest.mark.asyncio
async def test_a_strobe_fires_on_a_high_arousal_section_change():
    manager, par, mover, strobe = _rig()
    controller = _Controller()

    await apply_reactive_lighting(controller, ANALYSIS, fixtures=manager)

    strobe_writes = dict((write[1], write[2]) for write in controller.for_fixture(strobe, 4))
    assert strobe_writes[300] == 255
    assert strobe_writes[301] > 0, "a flash with no rate is a constant flood"
