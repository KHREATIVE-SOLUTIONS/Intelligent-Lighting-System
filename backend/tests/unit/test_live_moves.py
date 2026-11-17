"""
Live movement vocabulary
========================

The properties a lighting designer would check by eye, held as tests: every
pattern is mirror-symmetric about a truss's centre line, nothing leans a beam
into the audience's eyes, movements finish on a bar line, and the engine never
asks a head for a step it cannot make.
"""

import math

import pytest

from app.services.demo.venue_presets import create_venue_rig
from app.services.effects import live_moves
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine

SECTIONS = sorted(live_moves.SECTION_MOTION)
BEATS = [i * 0.37 for i in range(0, 90)]


@pytest.mark.parametrize("pattern", live_moves.PATTERNS)
@pytest.mark.parametrize("row_dir", [-1.0, 1.0])
def test_left_and_right_heads_mirror_each_other(pattern, row_dir):
    """Same lean, opposite pan: the picture is symmetric about the centre line."""
    for section in SECTIONS:
        motion = live_moves.SECTION_MOTION[section]
        for u in (0.2, 0.6, 1.0):
            for beats in BEATS:
                left = live_moves.head_target(pattern, u=-u, row_dir=row_dir, row_index=1, beats=beats, motion=motion)
                right = live_moves.head_target(pattern, u=u, row_dir=row_dir, row_index=1, beats=beats, motion=motion)
                assert left[0] == pytest.approx(-right[0], abs=1e-9), (pattern, section, u, beats)
                assert left[1] == pytest.approx(right[1], abs=1e-9), (pattern, section, u, beats)


@pytest.mark.parametrize("pattern", live_moves.PATTERNS)
def test_no_beam_leans_past_the_limit(pattern):
    """A beam never reaches the horizontal, where it would be in people's eyes."""
    for section in SECTIONS:
        motion = live_moves.SECTION_MOTION[section]
        for u in (-1.0, -0.4, 0.0, 0.4, 1.0):
            for beats in BEATS:
                for amp in (1.0, 1.15):
                    _, tilt = live_moves.head_target(
                        pattern, u=u, row_dir=-1.0, row_index=0, beats=beats, motion=motion, amp=amp)
                    lean = -tilt  # a downstage-leaning truss leans with negative tilt
                    assert live_moves.LEAN_MIN_DEG - 1e-9 <= lean <= live_moves.LEAN_MAX_DEG + 1e-9


@pytest.mark.parametrize("pattern", live_moves.PATTERNS)
def test_a_movement_finishes_on_a_bar_line(pattern):
    """One cycle is a whole number of bars, so a move ends where the music does."""
    for section in SECTIONS:
        motion = live_moves.SECTION_MOTION[section]
        assert motion.cycle_beats % 4 == 0
        start = live_moves.head_target(pattern, u=0.6, row_dir=-1.0, row_index=0, beats=3.0, motion=motion)
        again = live_moves.head_target(
            pattern, u=0.6, row_dir=-1.0, row_index=0, beats=3.0 + motion.cycle_beats, motion=motion)
        assert start == pytest.approx(again, abs=1e-6)


def test_a_downstage_truss_fans_outward_too():
    """Pan turns the way the head leans, so the sign flips with the truss."""
    motion = live_moves.SECTION_MOTION["chorus"]
    out_pan, out_tilt = live_moves.head_target(
        "sym_tilt", u=1.0, row_dir=-1.0, row_index=0, beats=0.0, motion=motion)
    back_pan, back_tilt = live_moves.head_target(
        "sym_tilt", u=1.0, row_dir=1.0, row_index=0, beats=0.0, motion=motion)
    # Beam direction in the previs convention: x = -sin(tilt) * sin(pan).
    x_out = -math.sin(math.radians(out_tilt)) * math.sin(math.radians(out_pan))
    x_back = -math.sin(math.radians(back_tilt)) * math.sin(math.radians(back_pan))
    assert x_out > 0.05 and x_back > 0.05, "a right-hand head must fan to the right on either truss"
    assert out_tilt < 0 < back_tilt, "the two trusses lean toward each other"


def test_an_unknown_pattern_still_moves_symmetrically():
    motion = live_moves.SECTION_MOTION["verse"]
    left = live_moves.head_target("tilt_cross", u=-0.5, row_dir=-1.0, row_index=0, beats=1.0, motion=motion)
    right = live_moves.head_target("tilt_cross", u=0.5, row_dir=-1.0, row_index=0, beats=1.0, motion=motion)
    assert left[0] == pytest.approx(-right[0]) and left[1] == pytest.approx(right[1])


def test_every_section_pool_names_real_patterns():
    for section, pool in live_moves.SECTION_POOLS.items():
        assert len(pool) >= 2, section
        assert set(pool) <= set(live_moves.PATTERNS), section
    assert set(live_moves.DEFAULT_POOL) <= set(live_moves.PATTERNS)


def test_slew_never_exceeds_the_rate():
    assert live_moves.slew(0.0, 90.0, 240.0, 1 / 60) == pytest.approx(4.0)
    assert live_moves.slew(0.0, -90.0, 180.0, 1 / 60) == pytest.approx(-3.0)
    assert live_moves.slew(10.0, 11.0, 240.0, 1 / 60) == 11.0
    # A nonsense frame time falls back to one frame rather than a free jump.
    assert live_moves.slew(0.0, 90.0, 240.0, 0.0) == pytest.approx(4.0)
    assert live_moves.slew(0.0, 90.0, 240.0, 5.0) == pytest.approx(4.0)


def _club_engine() -> EffectsEngine:
    engine = EffectsEngine(EffectsConfig(fps=60.0, auto_mode=True, movement_enabled=True, dimmer_enabled=True))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    return engine


def _play(engine: EffectsEngine, frames: int, section_at=None):
    """Step the live renderer, returning every mover's (pan, tilt) per frame."""
    movers = [f for f in engine.fixtures.fixtures.values() if "pan" in f.channels]
    history = []
    dt = 1.0 / 60.0
    for i in range(frames):
        if section_at and i in section_at:
            engine._rebuild_section = section_at[i]
        engine.update_audio(energy=0.6, bass=0.5, mid=0.3, high=0.2, is_beat=(i % 28 == 0),
                            beat_number=i // 28, bpm=128.0)
        engine.update(delta_time=dt)
        history.append({f.id: (f.pan, f.tilt) for f in movers})
    return movers, history


def test_the_engine_moves_a_real_rig_symmetrically():
    """On the club rig, each mirrored pair holds opposite pan and equal tilt."""
    engine = _club_engine()
    movers, history = _play(engine, 600)
    by_row = {}
    for f in movers:
        by_row.setdefault(round(f.z, 2), []).append(f)
    pairs = []
    for row in by_row.values():
        for a in row:
            for b in row:
                if a.x < -0.05 and abs(a.x + b.x) < 1e-6:
                    pairs.append((a.id, b.id))
    assert len(pairs) == 8, "club_night has three mirrored trusses: 3 + 3 + 2 pairs"
    moved = 0.0
    for frame in history[60:]:
        for left, right in pairs:
            assert frame[left][0] == pytest.approx(-frame[right][0], abs=1e-6)
            assert frame[left][1] == pytest.approx(frame[right][1], abs=1e-6)
            moved = max(moved, abs(frame[left][0]))
    assert moved > 15.0, "the heads have to actually go somewhere"


def test_a_section_change_is_a_glide_not_a_jump():
    """The biggest step on the wire is what a head can travel in one frame."""
    engine = _club_engine()
    changes = {120: "drop", 240: "breakdown", 360: "chorus", 480: "buildup"}
    movers, history = _play(engine, 600, section_at=changes)
    max_pan = live_moves.MAX_PAN_DEG_PER_S / 60.0 + 1e-6
    max_tilt = live_moves.MAX_TILT_DEG_PER_S / 60.0 + 1e-6
    for before, after in zip(history[1:], history[2:]):
        for f in movers:
            assert abs(after[f.id][0] - before[f.id][0]) <= max_pan
            assert abs(after[f.id][1] - before[f.id][1]) <= max_tilt
