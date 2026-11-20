"""
Idle Look On Prolonged Silence
==============================

A quiet moment in a set stays black: a breakdown, a track change, half a
minute of nothing. Once the audio has been below the silence threshold for
`idle_look_after_seconds` (a minute unless configured) the rig fades to a
gentle, static, low look, and it goes back to the show when music returns.

Nothing here sleeps. The engine counts on its own clock, which only moves
when `update(dt)` is called, so a minute of silence is 3600 calls.

The tests that say what the blackout latch, the grand master and the strobe
channels do are read off the packets a fake socket was handed, because those
belong to the output stage in the transmitter and nowhere else. No socket is
opened and no packet leaves the process.
"""

import numpy as np
import pytest

from app.core.config import Settings
from app.services.dmx.dmx_controller import DMXController
from app.services.effects import effects_engine as E
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager
from tests.musical import metrics as M

FPS = 60
DT = 1.0 / FPS
LEVEL = 0.35


def _engine(**config):
    engine = M.build_engine(**config)
    assert _washes(engine), "harness engine has no wash fixtures"
    return engine


def _washes(engine):
    return [f for f in engine.fixtures.get_fixtures_in_group("all") if f.fixture_type == "wash"]


def _play(engine, seconds, energy=0.5, audio=True, each_frame=None):
    """Step the engine; feed one analysis block every third frame when `audio`.

    Returns every fixture's dimmer on every frame, and whether the idle look
    was up on that frame.
    """
    frames = int(round(seconds * FPS))
    dimmers, active = [], []
    for i in range(frames):
        if audio and i % 3 == 0:
            engine.update_audio(
                energy=energy, bass=energy, mid=energy, high=energy * 0.6,
                is_beat=energy > 0 and (i // 3) % 10 == 0, beat_number=i // 30, bpm=128.0,
                programme_level=0.5 if energy > 0 else 0.0,
            )
        engine.update(DT)
        if each_frame is not None:
            each_frame()
        dimmers.append([f.dimmer for f in engine.fixtures.get_fixtures_in_group("all")])
        active.append(engine.idle_look_active)
    return np.asarray(dimmers), np.asarray(active)


def _silence(engine, seconds, **kwargs):
    return _play(engine, seconds, energy=0.0, **kwargs)


# ---------------------------------------------------------------------------
# A quiet moment stays black
# ---------------------------------------------------------------------------


def test_thirty_seconds_of_silence_stays_black():
    engine = _engine()
    _play(engine, 4.0)

    quiet, active = _silence(engine, 30.0)

    assert not active.any()
    # The first seconds are the music's own decay; after that, nothing.
    assert quiet[5 * FPS:].max() == 0.0
    assert engine.silence_seconds == pytest.approx(30.0, abs=0.1)


def test_fifty_nine_seconds_of_silence_still_stays_black():
    engine = _engine()
    _play(engine, 4.0)

    quiet, active = _silence(engine, 59.0)

    assert not active.any()
    assert not engine.idle_look_active
    assert quiet[5 * FPS:].max() == 0.0
    assert engine._idle_mix == 0.0


# ---------------------------------------------------------------------------
# A long silence brings the idle look up
# ---------------------------------------------------------------------------


def test_a_minute_of_silence_fades_to_the_idle_look():
    engine = _engine()
    _play(engine, 4.0)
    _silence(engine, 59.0)

    arriving, active = _silence(engine, 2.5)   # 59.0 s to 61.5 s

    assert not active[0] and active[-1], "the look comes up at the minute, not before"
    assert engine.idle_look_active
    # It fades in: part of the way there, and never a step.
    assert 0.0 < engine._idle_mix < 1.0
    assert 0.0 < arriving[-1].max() < LEVEL
    assert np.diff(arriving, axis=0).max() < 0.01
    assert np.all(np.diff(arriving.max(axis=1)) >= -1e-9)

    settled, _ = _silence(engine, 3.0)         # past the three second fade

    assert engine._idle_mix == 1.0
    for fixture in _washes(engine):
        assert fixture.dimmer == pytest.approx(LEVEL, abs=0.005)
        assert fixture.strobe == 0.0
        # Warm: red over green over blue.
        assert fixture.red > fixture.green > fixture.blue
    assert all(f.strobe == 0.0 for f in engine.fixtures.fixtures.values())
    # Static, and modest: nothing above the look's own level.
    assert settled[-FPS:].max() <= LEVEL + 0.005
    assert np.ptp(settled[-FPS:], axis=0).max() < 1e-6


def test_the_look_holds_its_heads_still():
    engine = _engine(idle_look_after_seconds=3.0, idle_look_fade_seconds=0.5)
    _silence(engine, 5.0)
    movers = [f for f in engine.fixtures.fixtures.values() if "pan" in f.channels]
    assert movers
    before = [(f.pan, f.tilt) for f in movers]

    _silence(engine, 3.0)

    assert engine.idle_look_active
    assert [(f.pan, f.tilt) for f in movers] == pytest.approx(before, abs=1e-6)


# ---------------------------------------------------------------------------
# Music coming back
# ---------------------------------------------------------------------------


def test_music_returning_recovers_the_show_and_resets_the_count():
    engine = _engine(idle_look_after_seconds=6.0, idle_look_fade_seconds=1.0)
    _play(engine, 3.0)
    _silence(engine, 9.0)
    assert engine.idle_look_active and engine._idle_mix == 1.0

    back, active = _play(engine, 4.0)

    # Promptly: gone inside the debounce, and faded out a second after that.
    gone_after = np.argmin(active) / FPS
    assert gone_after <= engine.config.idle_look_resume_seconds + 0.1
    assert not engine.idle_look_active
    assert engine._idle_mix == 0.0
    assert engine.silence_seconds == 0.0
    # The show is back, not the look: lit, and following the music again.
    assert back[-FPS:].max() > 0.0
    louder, _ = _play(engine, 3.0, energy=0.9)
    assert louder[-FPS:].mean() > back[-FPS:].mean() + 0.05
    _play(engine, 1.0)

    # The count starts again from nothing: five more quiet seconds are just
    # a quiet moment, and the rig is black through the end of them.
    quiet, active = _silence(engine, 5.0)
    assert not active.any()
    assert quiet[-FPS:].max() == 0.0
    assert engine.silence_seconds == pytest.approx(5.0, abs=0.1)


def test_the_idle_look_leaves_no_trace_on_the_show_that_follows():
    """Same music, same silence, with the look and without: the same show after.

    On one pinned clock, because parts of the engine read the wall clock and
    two runs otherwise differ by when they happened to be scheduled.
    """
    def show(after):
        clock = M._Clock()

        def tick():
            clock.t += DT

        with M.virtual_clock(clock):
            engine = _engine(idle_look_after_seconds=after, idle_look_fade_seconds=1.0)
            _play(engine, 3.0, each_frame=tick)
            _, idle = _silence(engine, 9.0, each_frame=tick)
            back, _ = _play(engine, 4.0, each_frame=tick)
            louder, _ = _play(engine, 3.0, energy=0.9, each_frame=tick)
        return idle[-1], back, louder

    was_idle, back, louder = show(6.0)
    never_idle, expected_back, expected_louder = show(0)

    assert was_idle and not never_idle
    # The first second and a half is the debounce and the fade out.
    assert back[2 * FPS:] == pytest.approx(expected_back[2 * FPS:], abs=1e-9)
    assert louder == pytest.approx(expected_louder, abs=1e-9)
    assert louder.max() > 0.5


def _kicks(engine, seconds, bpm=128.0, loud_blocks=2):
    """A dry four-on-the-floor: a couple of loud blocks on each beat, nothing between."""
    period = 60.0 / bpm
    active = []
    last_beat = -1
    loud_left = 0
    start = engine.time
    for i in range(int(round(seconds * FPS))):
        if i % 3 == 0:
            beat = int((engine.time - start) / period)
            hit = beat != last_beat
            if hit:
                last_beat, loud_left = beat, loud_blocks
            energy = 0.8 if loud_left > 0 else 0.0
            loud_left -= 1
            engine.update_audio(energy=energy, bass=energy, is_beat=hit, beat_number=beat,
                                bpm=bpm, programme_level=0.5)
        engine.update(DT)
        active.append(engine.idle_look_active)
    return np.asarray(active)


def test_a_kick_playing_on_its_own_still_ends_the_look():
    """Music is not unbroken level: between the hits of a dry kick there is nothing."""
    engine = _engine(idle_look_after_seconds=4.0, idle_look_fade_seconds=0.5)
    _silence(engine, 6.0)
    assert engine.idle_look_active

    active = _kicks(engine, 6.0)

    assert not active[-1]
    assert np.argmin(active) / FPS <= 3.0, "the look must not sit over a track that has started"
    assert not active[np.argmin(active):].any(), "and once gone it stays gone"


def test_sparse_music_is_never_counted_as_a_long_silence():
    engine = _engine(idle_look_after_seconds=4.0)

    active = _kicks(engine, 12.0)

    assert not active.any()
    assert engine.silence_seconds < 1.0


def test_the_legacy_renderer_gets_the_look_too():
    engine = _engine(idle_look_after_seconds=3.0, idle_look_fade_seconds=0.5)
    engine._rebuild_busker_enabled = False

    _silence(engine, 6.0)

    assert engine.idle_look_active and engine._idle_mix == 1.0
    for fixture in _washes(engine):
        assert fixture.dimmer == pytest.approx(LEVEL, abs=0.005)
        assert fixture.strobe == 0.0
        assert fixture.red > fixture.green > fixture.blue


def test_a_short_blip_does_not_drop_the_look():
    engine = _engine(idle_look_after_seconds=4.0, idle_look_fade_seconds=0.5)
    _silence(engine, 6.0)
    assert engine.idle_look_active and engine._idle_mix == 1.0

    # A cable click: a fifth of a second of level, then nothing again.
    blip, during = _play(engine, 0.2, energy=0.8)
    after, later = _silence(engine, 2.0)

    assert during.all() and later.all(), "the look must not flap on a blip"
    assert engine._idle_mix == 1.0
    for frames in (blip, after):
        wash = frames[:, [i for i, f in enumerate(
            engine.fixtures.get_fixtures_in_group("all")) if f.fixture_type == "wash"]]
        assert wash == pytest.approx(LEVEL, abs=0.005)


def test_a_short_blip_does_not_restart_the_count():
    engine = _engine(idle_look_after_seconds=6.0)
    _silence(engine, 4.0)
    _play(engine, 0.2, energy=0.8)
    _, active = _silence(engine, 2.2)

    assert active[-1], "a blip in the fifth second must not buy another six"
    assert engine.silence_seconds == pytest.approx(6.4, abs=0.1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_the_wait_is_configurable():
    engine = _engine(idle_look_after_seconds=5.0)

    _, early = _silence(engine, 4.5)
    _, late = _silence(engine, 1.0)

    assert not early.any()
    assert late[-1]


@pytest.mark.parametrize("after", [0, 0.0, -1.0, float("nan"), None])
def test_zero_or_less_switches_the_idle_look_off(after):
    engine = _engine(idle_look_after_seconds=after)
    _play(engine, 3.0)

    quiet, active = _silence(engine, 70.0)

    assert not active.any()
    assert quiet[5 * FPS:].max() == 0.0
    assert engine.silence_seconds == 0.0
    assert engine.idle_look_status()["idle_look_after_seconds"] == 0.0


def test_the_look_and_its_level_are_configurable():
    engine = _engine(idle_look_after_seconds=2.0, idle_look_fade_seconds=0.2,
                     idle_look_name="cool_blue", idle_look_level=0.2)
    _silence(engine, 4.0)

    for fixture in _washes(engine):
        assert fixture.dimmer == pytest.approx(0.2, abs=0.005)
        assert fixture.blue > fixture.green > fixture.red
    assert engine.idle_look_status()["idle_look"] == "cool_blue"


def test_an_unknown_look_falls_back_to_the_default():
    engine = _engine(idle_look_after_seconds=2.0, idle_look_fade_seconds=0.2,
                     idle_look_name="disco inferno")
    _silence(engine, 4.0)

    assert engine.idle_look_status()["idle_look"] == E._IDLE_LOOK_DEFAULT
    for fixture in _washes(engine):
        assert fixture.dimmer == pytest.approx(LEVEL, abs=0.005)
        assert fixture.red > fixture.green > fixture.blue


def test_no_idle_look_ever_strobes_or_runs_bright():
    assert E._IDLE_LOOK_DEFAULT in E._IDLE_LOOKS
    assert "strobe" in E._IDLE_HELD_ATTRS
    assert 0.3 <= EffectsConfig().idle_look_level <= 0.4
    assert EffectsConfig().idle_look_after_seconds == 60.0


def test_the_settings_carry_the_idle_look(monkeypatch):
    assert Settings.model_fields["IDLE_LOOK_AFTER_SECONDS"].default == 60.0
    assert Settings.model_fields["IDLE_LOOK_NAME"].default in E._IDLE_LOOKS

    monkeypatch.setenv("IDLE_LOOK_AFTER_SECONDS", "0")
    monkeypatch.setenv("IDLE_LOOK_NAME", "warm_white")
    configured = Settings()

    assert configured.IDLE_LOOK_AFTER_SECONDS == 0.0
    assert configured.IDLE_LOOK_NAME == "warm_white"


# ---------------------------------------------------------------------------
# What does not count as a long silence
# ---------------------------------------------------------------------------


def test_an_input_the_operator_stopped_stays_dark():
    engine = _engine(idle_look_after_seconds=4.0, idle_look_fade_seconds=0.5)
    _play(engine, 3.0)

    engine.audio_input_stopped()
    after, active = _play(engine, 8.0, audio=False)

    assert not active.any()
    assert after[-FPS:].max() == 0.0


def test_stopping_the_input_takes_the_idle_look_down():
    engine = _engine(idle_look_after_seconds=3.0, idle_look_fade_seconds=0.5)
    _silence(engine, 5.0)
    assert engine.idle_look_active

    engine.audio_input_stopped()
    after, active = _play(engine, 3.0, audio=False)

    assert not active.any()
    assert after[-FPS:].max() == 0.0


def test_an_input_that_never_arrived_stays_dark():
    engine = _engine(idle_look_after_seconds=3.0)

    frames, active = _play(engine, 6.0, audio=False)

    assert not active.any()
    assert frames.max() == 0.0


def test_a_look_set_by_hand_is_left_alone():
    engine = _engine(idle_look_after_seconds=3.0)
    engine.set_auto_mode(False)

    _, active = _silence(engine, 6.0)

    assert not active.any()
    assert engine._idle_mix == 0.0


def test_emitters_the_look_borrowed_are_handed_back():
    engine = _engine(idle_look_after_seconds=3.0, idle_look_fade_seconds=0.5)
    bar = next(f for f in engine.fixtures.fixtures.values() if "uv" in f.channels)
    bar.uv = 0.6

    _silence(engine, 5.0)
    assert engine.idle_look_active and bar.uv == 0.0

    _play(engine, 3.0)
    assert not engine.idle_look_active
    assert bar.uv == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_the_status_payload_reports_the_idle_state():
    engine = _engine(idle_look_after_seconds=5.0, idle_look_fade_seconds=1.0)
    _play(engine, 2.0)

    playing = engine.get_pro_lighting_state()
    assert playing["idle_look_active"] is False
    assert playing["silence_seconds"] == 0.0
    assert playing["idle_look_after_seconds"] == 5.0

    _silence(engine, 3.0)
    waiting = engine.get_pro_lighting_state()
    assert waiting["idle_look_active"] is False
    assert waiting["silence_seconds"] == pytest.approx(3.0, abs=0.1)

    _silence(engine, 4.0)
    idle = engine.get_pro_lighting_state()
    assert idle["idle_look_active"] is True
    assert idle["silence_seconds"] == pytest.approx(7.0, abs=0.1)
    assert idle["idle_look"] == "warm_amber"
    assert idle["idle_look_mix"] == 1.0

    # The same fields with the pro layer off, and on their own for the
    # websocket payload.
    engine.enable_pro_lighting(False)
    off = engine.get_pro_lighting_state()
    assert off["enabled"] is False and off["idle_look_active"] is True
    assert engine.idle_look_status()["idle_look_active"] is True


# ---------------------------------------------------------------------------
# At the wire: the output stage still owns the room
# ---------------------------------------------------------------------------

WASH = {'pan': 0, 'tilt': 1, 'dimmer': 2, 'shutter': 3, 'red': 4, 'green': 5, 'blue': 6,
        'white': 7}
BAR = {'dimmer': 0, 'strobe': 1, 'red': 2, 'green': 3, 'blue': 4, 'amber': 5}
STROBE = {'dimmer': 0, 'strobe': 1}
PAR_NO_DIMMER = {'red': 0, 'green': 1, 'blue': 2}

WASH_DIMMERS = (2, 10)      # 0-based slots
WASH_PAN_TILT = (0, 1, 8, 9)
BAR_DIMMER, BAR_STROBE = 20, 21
STROBE_DIMMER, STROBE_RATE = 30, 31
PAR_RED, PAR_GREEN, PAR_BLUE = 40, 41, 42
IDLE_BYTE = round(LEVEL * 255)
# Every slot that carries intensity: the dimmers, and the colours of the par
# that has no dimmer. A colour behind a dimmer is not light while that is shut.
INTENSITY = WASH_DIMMERS + (BAR_DIMMER, STROBE_DIMMER, PAR_RED, PAR_GREEN, PAR_BLUE)


class Recorder:
    """Stands in for the UDP socket. Keeps what it was asked to send."""

    def __init__(self):
        self.packets = []

    def sendto(self, packet, target):
        assert packet[:8] == b'Art-Net\x00'
        self.packets.append(np.frombuffer(bytes(packet[18:]), dtype=np.uint8))

    def close(self):
        pass


@pytest.fixture
def controller():
    ctrl = DMXController()
    ctrl.config.ip_address = "127.0.0.1"
    ctrl.config.broadcast = False
    ctrl.socket = Recorder()
    ctrl.is_connected = True   # no thread: the tests step the transmitter
    return ctrl


def _wire_engine(controller, **config):
    """An engine wired to the controller the way main.py wires it."""
    manager = FixtureGroupManager()
    manager.add_fixtures([
        Fixture(id="wash0", name="Wash 0", dmx_address=1, channels=dict(WASH), fixture_type="wash"),
        Fixture(id="wash1", name="Wash 1", dmx_address=9, channels=dict(WASH), fixture_type="wash"),
        Fixture(id="bar0", name="Bar 0", dmx_address=21, channels=dict(BAR), fixture_type="bar"),
        Fixture(id="strobe0", name="Strobe 0", dmx_address=31, channels=dict(STROBE),
                fixture_type="strobe"),
        Fixture(id="par0", name="Par 0", dmx_address=41, channels=dict(PAR_NO_DIMMER),
                fixture_type="par"),
    ])
    settings = dict(idle_look_after_seconds=2.0, idle_look_fade_seconds=0.5)
    settings.update(config)
    # Strobes allowed, so the stage is not what keeps the strobe fixture off.
    engine = EffectsEngine(EffectsConfig(
        fps=FPS, strobe_enabled=True, accessibility_mode="performance",
        strobe_hz_cap=10.0, **settings,
    ))
    engine.set_fixture_manager(manager)
    engine.set_dmx_callback(controller.write_universe)
    engine.attach_output_stage(controller.output_stage)
    return engine


def _wire_silence(engine, controller, seconds):
    """Silence, with the transmitter stepped on the engine's clock. Returns what was sent."""
    start = len(controller.socket.packets)
    _silence(engine, seconds, each_frame=lambda: controller._transmit_frame(engine.time))
    return np.asarray(controller.socket.packets[start:])


def test_the_idle_look_reaches_the_wire_with_no_strobe(controller):
    engine = _wire_engine(controller)
    # Something left the bar's strobe channel running. Nothing in the show
    # clears it, so it is on the wire until the look takes it over.
    bar = engine.fixtures.fixtures["bar0"]
    bar.strobe = 0.8

    sent = _wire_silence(engine, controller, 4.0)

    assert engine.idle_look_active
    assert sent[:FPS][:, INTENSITY].max() == 0, "the first second of silence is black"
    assert sent[:FPS][:, BAR_STROBE].min() == 204
    assert sent[int(2.1 * FPS):][:, BAR_STROBE].max() == 0, "no strobe once the look begins"
    last = sent[-1]
    for slot in WASH_DIMMERS + (BAR_DIMMER, PAR_RED):
        assert last[slot] == pytest.approx(IDLE_BYTE, abs=1)
    assert last[PAR_RED] > last[PAR_GREEN] > last[PAR_BLUE] > 0, "a warm amber"
    # No strobe anywhere, from the first frame of the fade to the last: the
    # bar's rate channel at zero, and the strobe fixture entirely off.
    assert last[BAR_STROBE] == 0 and bar.strobe == 0.0
    assert sent[:, STROBE_DIMMER].max() == 0 and sent[:, STROBE_RATE].max() == 0
    # A shutter that is not strobing is open, at 255.
    assert last[3] == 255 and last[11] == 255
    # And it arrived as a fade, well under anything the stage calls a flash.
    assert np.diff(sent[:, WASH_DIMMERS[0]].astype(int)).max() <= 4
    assert controller.output_stage.limited_frames == 0


def test_a_blackout_latch_wins_over_the_idle_look(controller):
    engine = _wire_engine(controller)
    lit = _wire_silence(engine, controller, 4.0)
    assert lit[-1][WASH_DIMMERS[0]] == pytest.approx(IDLE_BYTE, abs=1)

    engine.blackout()
    dark = _wire_silence(engine, controller, 2.0)

    assert engine.idle_look_active, "the look is still what the engine is rendering"
    assert controller.output_stage.blackout_active
    assert dark[:, INTENSITY].max() == 0

    engine.restore()
    back = _wire_silence(engine, controller, 2.0)
    assert back[-1][WASH_DIMMERS[0]] == pytest.approx(IDLE_BYTE, abs=1)
    assert back[-1][PAR_RED] == pytest.approx(IDLE_BYTE, abs=1)


def test_a_latch_set_before_the_minute_keeps_the_room_dark_through_it(controller):
    engine = _wire_engine(controller)
    engine.blackout()

    sent = _wire_silence(engine, controller, 5.0)

    assert engine.idle_look_active and engine._idle_mix == 1.0
    assert sent[:, INTENSITY].max() == 0


def test_the_idle_look_respects_the_grand_master(controller):
    engine = _wire_engine(controller)
    full = _wire_silence(engine, controller, 4.0)[-1]

    engine.set_grand_master(0.5)
    half = _wire_silence(engine, controller, 1.0)[-1]

    for slot in WASH_DIMMERS + (BAR_DIMMER, PAR_RED):
        assert full[slot] == pytest.approx(IDLE_BYTE, abs=1)
        assert half[slot] == pytest.approx(IDLE_BYTE / 2, abs=1)
    for slot in WASH_PAN_TILT:
        assert half[slot] == full[slot], "pulling the master down must never move a head"

    engine.set_grand_master(0.0)
    none = _wire_silence(engine, controller, 0.5)[-1]
    assert none[list(INTENSITY)].max() == 0
