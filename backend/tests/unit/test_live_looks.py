"""
Looks: a position, a motion, and an aim
=======================================

Checked where it matters, in beam space: does the beam land on the point it
was aimed at, do the two halves of a truss mirror each other, does anything
lean into people's eyes, and can a real head keep up. Every check runs on
every demo rig, because the point of aiming at the room rather than setting
angles is that a look is the same picture on any of them.
"""

import math

import pytest

from app.services.demo.venue_presets import VENUE_PRESETS, create_venue_rig
from app.services.effects import live_looks as LL
from app.services.effects import live_moves
from app.services.effects.effects_engine import _CLUB_STYLE_LOOKS, EffectsConfig, EffectsEngine
from tests.musical import metrics as M

RIGS = sorted(VENUE_PRESETS)
SECTIONS = sorted(LL.SECTION_MOTION)
BEATS = [i * 0.31 for i in range(0, 60)]


def rig_of(name: str) -> LL.Rig:
    manager, _ = create_venue_rig(name)
    return LL.build_rig([f for f in manager.fixtures.values() if "pan" in f.channels and "tilt" in f.channels])


def mirror_pairs(rig: LL.Rig):
    pairs = []
    for a in rig.heads:
        if a.u >= -1e-6:
            continue
        for b in rig.heads:
            if b.row == a.row and abs(b.u + a.u) < 1e-6 and abs(b.y - a.y) < 1e-6:
                pairs.append((a, b))
                break
    return pairs


def test_the_beam_direction_is_the_3d_views():
    """The vector three.js gives for tilt -40, pan +60 with a YXZ head."""
    assert LL.beam_direction(60.0, -40.0) == pytest.approx((0.557, -0.766, 0.321), abs=2e-3)
    assert LL.beam_direction(0.0, 0.0) == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)
    # Negative tilt leans downstage, toward the audience.
    assert LL.beam_direction(0.0, -30.0)[2] > 0


@pytest.mark.parametrize("rig_name", RIGS)
def test_a_beam_lands_on_the_point_it_was_aimed_at(rig_name):
    rig = rig_of(rig_name)
    checked = 0
    for look, cfg in LL.LOOKS.items():
        if cfg.motion == "fly":
            continue
        for section in SECTIONS:
            motion = LL.SECTION_MOTION[section]
            for beats in BEATS[::6]:
                for head in rig.heads:
                    target = LL.head_target(look, head, rig, beats, motion)
                    lean = math.degrees(math.atan2(
                        math.hypot(target[0] - head.x, target[2] - head.z), head.y - target[1]))
                    if lean > LL.LEAN_MAX_DEG - 0.01:
                        continue  # held back by the lean limit, on purpose
                    spot = LL.landing(head, *LL.aim(head, target))
                    assert spot == pytest.approx(target, abs=1e-6), (look, section, head.fid)
                    checked += 1
    assert checked > 100


@pytest.mark.parametrize("rig_name", RIGS)
def test_left_and_right_heads_mirror_each_other(rig_name):
    """Opposite pan, same tilt: the picture is symmetric about the centre line."""
    rig = rig_of(rig_name)
    pairs = mirror_pairs(rig)
    assert pairs, "every demo rig is hung symmetrically"
    for look in LL.LOOKS:
        for section in SECTIONS:
            motion = LL.SECTION_MOTION[section]
            for beats in BEATS[::5]:
                for left, right in pairs:
                    pl, tl = LL.head_pan_tilt(look, left, rig, beats, motion)
                    pr, tr = LL.head_pan_tilt(look, right, rig, beats, motion)
                    assert pl == pytest.approx(-pr, abs=1e-9), (look, section, left.fid)
                    assert tl == pytest.approx(tr, abs=1e-9), (look, section, left.fid)


@pytest.mark.parametrize("rig_name", RIGS)
def test_no_beam_leans_too_far_or_turns_past_a_quarter(rig_name):
    """Nothing near the horizontal, and no head asked to swap to its other answer."""
    rig = rig_of(rig_name)
    for look in LL.LOOKS:
        for section in SECTIONS:
            motion = LL.SECTION_MOTION[section]
            for beats in BEATS[::4]:
                for head in rig.heads:
                    pan, tilt = LL.head_pan_tilt(look, head, rig, beats, motion, speed=1.25, amp=1.15)
                    assert abs(tilt) <= LL.LEAN_MAX_DEG + 1e-9
                    assert abs(pan) < 90.0, (look, section, head.fid, pan)
                    # A truss keeps the tilt sign it was given for the life of the rig.
                    assert tilt * head.row_dir >= -1e-9


@pytest.mark.parametrize("rig_name", RIGS)
@pytest.mark.parametrize("bpm,speed,amp", [(128.0, 1.0, 1.0), (128.0, 1.25, 1.15), (174.0, 1.0, 1.0)])
def test_a_steady_look_never_asks_for_more_than_a_head_can_do(rig_name, bpm, speed, amp):
    """So the slew limit only ever acts at a change of look, never inside one."""
    rig = rig_of(rig_name)
    beats_per_frame = bpm / 60.0 / 60.0
    step = 3
    max_pan = step * live_moves.MAX_PAN_DEG_PER_S / 60.0
    max_tilt = step * live_moves.MAX_TILT_DEG_PER_S / 60.0
    for look in LL.LOOKS:
        for section in ("verse", "chorus", "drop"):
            motion = LL.SECTION_MOTION[section]
            frames = int(2.0 * motion.cycle_beats / beats_per_frame) + step
            for head in rig.heads[:: max(1, len(rig.heads) // 4)]:
                last = None
                for i in range(0, frames, step):
                    now = LL.head_pan_tilt(look, head, rig, i * beats_per_frame, motion, speed, amp)
                    if last is not None:
                        assert abs(now[0] - last[0]) <= max_pan, (look, section, head.fid, bpm)
                        assert abs(now[1] - last[1]) <= max_tilt, (look, section, head.fid, bpm)
                    last = now


@pytest.mark.parametrize("rig_name", RIGS)
def test_the_focus_is_in_front_of_every_truss(rig_name):
    """A head never has the point it plays to behind it or under it."""
    rig = rig_of(rig_name)
    for head in rig.heads:
        assert (rig.focus[2] - head.z) * head.forward > 0.0, head.fid


def test_a_fly_out_starts_gathered_and_opens_to_the_fan():
    rig = rig_of("club_night")
    motion = LL.SECTION_MOTION["drop"]
    head = rig.heads[0]
    gathered = LL.aim(head, LL.POSITIONS["centre"](head, rig))
    fanned = LL.aim(head, LL.POSITIONS["fan"](head, rig))
    assert LL.head_pan_tilt("centre_fly_fan", head, rig, 0.0, motion) == pytest.approx(gathered)
    # Half way through its two cycles it is fully open.
    assert LL.head_pan_tilt("centre_fly_fan", head, rig, motion.cycle_beats, motion) == pytest.approx(fanned)
    assert gathered != pytest.approx(fanned)


def test_all_centre_puts_every_beam_on_one_point():
    rig = rig_of("club_night")
    spots = [LL.landing(h, *LL.aim(h, LL.POSITIONS["centre"](h, rig))) for h in rig.heads]
    for spot in spots:
        assert spot == pytest.approx(rig.focus, abs=1e-6)


def test_a_cross_sends_each_side_over_the_centre_line():
    rig = rig_of("club_night")
    for head in rig.heads:
        target = LL.POSITIONS["cross"](head, rig)
        if abs(head.u) > 1e-6:
            assert (target[0] - rig.x_mid) * (head.x - rig.x_mid) < 0, head.fid


def test_a_head_that_is_turned_round_still_hits_the_target():
    rig = rig_of("club_night")
    straight = rig.heads[0]
    turned = LL.Head(**{**straight.__dict__, "yaw": 90.0})
    target = LL.POSITIONS["fan"](straight, rig)
    pan_a, tilt_a = LL.aim(straight, target)
    pan_b, tilt_b = LL.aim(turned, target)
    assert pan_b == pytest.approx(pan_a - 90.0)
    assert tilt_b == pytest.approx(tilt_a)
    assert LL.landing(turned, pan_b, tilt_b) == pytest.approx(target, abs=1e-6)


def test_a_held_look_does_not_move():
    rig = rig_of("club_night")
    motion = LL.SECTION_MOTION["drop"]
    for head in rig.heads:
        first = LL.head_pan_tilt("cross_hold", head, rig, 0.0, motion)
        for beats in BEATS:
            assert LL.head_pan_tilt("cross_hold", head, rig, beats, motion) == first


def test_the_generated_movements_are_every_sensible_combination():
    assert LL.DEFAULT_LOOK in LL.LOOKS
    for name, look in LL.LOOKS.items():
        assert look.position in LL.POSITIONS, name
        assert look.motion in ("hold", "tilt", "sweep", "circle", "fly"), name
        assert look.phase in LL.PHASES, name
        assert (look.to in LL.POSITIONS) if look.motion == "fly" else (look.to is None), name
    # 4 positions x (hold + 3 motions x 3 phases) + the fly-outs.
    assert len(LL.LOOKS) == 4 * (1 + 3 * 3) + len(LL.FLY_PAIRS)


def test_every_club_style_leans_toward_real_movements():
    for style, spec in _CLUB_STYLE_LOOKS.items():
        if spec["patterns"] is not None:
            assert len(set(spec["patterns"]) & set(LL.LOOKS)) >= 2, style
            assert set(spec["patterns"]) <= set(LL.LOOKS), style


def test_an_unknown_look_falls_back_to_a_real_one():
    rig = rig_of("club_night")
    head = rig.heads[0]
    motion = LL.SECTION_MOTION["verse"]
    assert LL.head_pan_tilt("tilt_cross", head, rig, 1.0, motion) == \
        LL.head_pan_tilt(LL.DEFAULT_LOOK, head, rig, 1.0, motion)


# ---------------------------------------------------------------------------
# Through the engine
# ---------------------------------------------------------------------------

# The look library chooses at random. What follows has to hold whatever it chooses.
SEEDS = (1, 2, 3, 4)


def _club_engine(seed: int = 1) -> EffectsEngine:
    engine = EffectsEngine(EffectsConfig(fps=60.0, auto_mode=True, movement_enabled=True, dimmer_enabled=True,
                                         look_seed=seed))
    manager, _ = create_venue_rig("club_night")
    engine.set_fixture_manager(manager)
    return engine


def _play(engine: EffectsEngine, frames: int, section_at=None):
    movers = [f for f in engine.fixtures.fixtures.values() if "pan" in f.channels]
    history = []
    clock = M._Clock()
    # On the virtual clock, so a run that fails fails again: the beat clock
    # places each audio block inside its frame by the wall clock.
    with M.virtual_clock(clock):
        for i in range(frames):
            clock.t = (i + 1) / 60.0
            if section_at and i in section_at:
                # Held as an operator's button holds it; a section merely written
                # here is overwritten by the detector on the next frame.
                engine._force_section(section_at[i], 1e9)
            engine.update_audio(energy=0.6, bass=0.5, mid=0.3, high=0.2, is_beat=(i % 28 == 0),
                                beat_number=i // 28, bpm=128.0)
            engine.update(delta_time=1.0 / 60.0)
            history.append({f.id: (f.pan, f.tilt) for f in movers})
    return movers, history


@pytest.mark.parametrize("seed", SEEDS)
def test_the_engine_moves_a_real_rig_symmetrically(seed):
    engine = _club_engine(seed)
    sections = {0: "verse", 150: "chorus", 300: "drop", 450: "buildup"}
    movers, history = _play(engine, 600, section_at=sections)
    pairs = [(a.id, b.id) for a in movers for b in movers
             if abs(a.z - b.z) < 1e-6 and a.x < -0.05 and abs(a.x + b.x) < 1e-6]
    assert len(pairs) == 8, "club_night has three mirrored trusses: 3 + 3 + 2 pairs"
    moved = 0.0
    for frame in history[60:]:
        for left, right in pairs:
            assert frame[left][0] == pytest.approx(-frame[right][0], abs=1e-6)
            assert frame[left][1] == pytest.approx(frame[right][1], abs=1e-6)
            moved = max(moved, abs(frame[left][1]))
    assert moved > 15.0, "the heads have to actually go somewhere"


@pytest.mark.parametrize("seed", SEEDS)
def test_a_section_change_is_a_glide_not_a_jump(seed):
    engine = _club_engine(seed)
    changes = {120: "drop", 240: "breakdown", 360: "chorus", 480: "buildup"}
    movers, history = _play(engine, 600, section_at=changes)
    assert engine._rebuild_section == "buildup", "the sections really did change"
    max_pan = live_moves.MAX_PAN_DEG_PER_S / 60.0 + 1e-6
    max_tilt = live_moves.MAX_TILT_DEG_PER_S / 60.0 + 1e-6
    for before, after in zip(history[1:], history[2:]):
        for f in movers:
            assert abs(after[f.id][0] - before[f.id][0]) <= max_pan
            assert abs(after[f.id][1] - before[f.id][1]) <= max_tilt
