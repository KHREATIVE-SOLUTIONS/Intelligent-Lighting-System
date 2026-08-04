"""The accent layer, tested where the harm would be.

Photosensitive epilepsy is the one failure mode in this project that hurts a
person rather than a show, so the properties asserted here are the ones a venue
owner is entitled to assume: `no_strobe` is a complete off switch, the flash
rate cannot be configured above the venue cap, and the genre budget is what
decides how often a song is punctuated.

The governor is driven directly with numbers rather than through a rendered
show wherever that is possible; `tests/musical` is where the same properties
are checked against real DMX.
"""

import pytest

from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.lighting.genre_profiles import Genre
from app.services.lighting.pro_effects import (
    ACCENT_HZ_HARD_CEILING,
    ACCENT_MIN_HZ_CAP,
    AccentGovernor,
    AccentPosture,
    ProStrobe,
    ProStrobeMode,
    attach_accent_governor,
)

FPS = 60.0
DT = 1.0 / FPS

# A drop as the governor sees it: loud, and the low end arrives.
DROP = dict(energy=0.85, bass=0.95)
BUILD = dict(energy=0.45, bass=0.20)
QUIET = dict(energy=0.02, bass=0.02)


def governor(genre: str = "edm", posture: AccentPosture = None) -> AccentGovernor:
    strobe = ProStrobe()
    strobe.set_genre(genre)
    return AccentGovernor(strobe, posture)


def config(**overrides) -> EffectsConfig:
    base = dict(
        strobe_enabled=True,
        accessibility_mode="conservative",
        strobe_hz_cap=3.0,
        strobe_max_duty_cycle=0.34,
    )
    base.update(overrides)
    return EffectsConfig(**base)


def play(gov: AccentGovernor, cfg, seconds: float, *, start: float = 0.0,
         section: str = "verse", **features):
    """Run the governor over a stretch of steady programme.

    Returns the times at which the accent flag was on, so a caller can count
    windows and measure the gaps between them.
    """
    on = []
    frames = int(round(seconds * FPS))
    for i in range(frames):
        now = start + i * DT
        gov.tick(now=now, delta_time=DT, section=section, config=cfg, **features)
        if cfg.strobe_enabled:
            on.append(now)
    return on


def windows(times, gap: float = 0.5):
    """Group contiguous on-frames into accents."""
    out = []
    for t in times:
        if not out or t - out[-1][-1] > gap:
            out.append([t])
        else:
            out[-1].append(t)
    return out


# ---------------------------------------------------------------------------
# The off switch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("policy", ["no_strobe", "nostrobe", "off", "safe"])
def test_no_strobe_policies_never_let_the_flag_on(policy):
    gov = governor()
    cfg = config(accessibility_mode=policy)
    assert play(gov, cfg, 30.0, section="drop", **DROP) == []
    assert gov.telemetry.accents == 0
    assert gov.strobe.strobe_budget_remaining == 999


@pytest.mark.parametrize("kwargs", [
    dict(camera_mode=True),
    dict(venue_mode="theatre"),
    dict(venue_mode="broadcast"),
    dict(venue_mode="corporate"),
])
def test_visibility_first_contexts_are_also_a_complete_off_switch(kwargs):
    gov = governor()
    cfg = config(**kwargs)
    assert play(gov, cfg, 30.0, section="drop", **DROP) == []


def test_an_operator_switching_accents_off_mid_show_is_obeyed():
    """The master switch has to hold, and let go again."""
    gov = governor()
    cfg = config()
    assert windows(play(gov, cfg, 20.0, section="drop", **DROP))

    gov.set_enabled(False)
    assert play(gov, cfg, 60.0, start=20.0, section="drop", **DROP) == []

    gov.set_enabled(True)
    assert windows(play(gov, cfg, 30.0, start=80.0, section="drop", **DROP))


def test_switching_the_config_flag_off_during_an_accent_is_obeyed():
    """`config.strobe_enabled` is still observed whenever it can be."""
    gov = governor()
    cfg = config()
    on = []
    for i in range(int(40.0 * FPS)):
        now = i * DT
        gov.tick(now=now, delta_time=DT, section="drop", config=cfg, **DROP)
        if cfg.strobe_enabled:
            on.append(now)
            cfg.strobe_enabled = False  # operator kills it mid-accent
    assert len(on) == 1
    assert play(gov, cfg, 60.0, start=40.0, section="drop", **DROP) == []


def test_the_governor_leaves_an_operator_intensity_cap_alone():
    gov = governor()
    cfg = config(audience_intensity_cap=0.6)
    play(gov, cfg, 10.0, **BUILD)
    assert cfg.audience_intensity_cap == pytest.approx(0.6, abs=1e-6)


# ---------------------------------------------------------------------------
# The venue governor
# ---------------------------------------------------------------------------


def test_a_hostile_venue_file_cannot_raise_the_flash_rate():
    gov = governor()
    cfg = config(
        accessibility_mode="performance",
        strobe_hz_cap=999.0,
        strobe_max_duty_cycle=0.99,
        strobe_burst_max_s=10.0,
        strobe_refractory_s=0.0,
    )
    play(gov, cfg, 5.0, section="drop", **DROP)

    assert cfg.strobe_hz_cap == ACCENT_HZ_HARD_CEILING
    assert cfg.strobe_max_duty_cycle <= 0.42
    assert cfg.strobe_burst_max_s <= 0.10
    assert cfg.strobe_refractory_s >= 0.30
    assert gov.telemetry.hz_clamps >= 1


def test_the_conservative_posture_holds_three_flashes_a_second():
    gov = governor()
    cfg = config(accessibility_mode="conservative", strobe_hz_cap=999.0)
    play(gov, cfg, 5.0, section="drop", **DROP)
    assert cfg.strobe_hz_cap == 3.0
    assert cfg.strobe_max_duty_cycle <= 0.34


def test_a_venue_cap_tighter_than_the_posture_is_respected():
    gov = governor()
    cfg = config(strobe_hz_cap=1.5)
    play(gov, cfg, 5.0, section="drop", **DROP)
    assert cfg.strobe_hz_cap == pytest.approx(1.5)


def test_a_zero_hz_cap_is_lifted_off_zero():
    """At 0 Hz the renderer's `(t*hz) % 1 < duty` is permanently true, which is
    a held blinder rather than the darkness a zero would suggest."""
    gov = governor()
    cfg = config(strobe_hz_cap=0.0)
    play(gov, cfg, 2.0, section="drop", **DROP)
    assert cfg.strobe_hz_cap >= ACCENT_MIN_HZ_CAP


# ---------------------------------------------------------------------------
# The genre budget
# ---------------------------------------------------------------------------


def test_jazz_gets_no_accents_at_all():
    gov = governor("jazz")
    cfg = config()
    assert play(gov, cfg, 120.0, section="drop", **DROP) == []
    assert gov.telemetry.accents == 0
    assert gov.telemetry.refused_by_budget > 0


def test_rock_gets_three_a_song_and_then_stops():
    gov = governor("rock")
    cfg = config()
    on = play(gov, cfg, 300.0, section="drop", **DROP)
    assert len(windows(on)) == 3
    assert gov.budget_remaining == 0

    gov.reset_song()
    assert len(windows(play(gov, cfg, 300.0, start=300.0, section="drop", **DROP))) == 3


def test_a_sustained_drop_cannot_machine_gun_the_room():
    """The old live path could re-arm roughly six times a second, forever."""
    gov = governor("edm")
    cfg = config()
    on = play(gov, cfg, 120.0, section="drop", **DROP)
    found = windows(on)

    assert 1 <= len(found) <= 12
    starts = [w[0] for w in found]
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= gov.posture.min_gap_s for g in gaps), gaps
    assert all(len(w) * DT <= gov.posture.window_s + DT for w in found)


def test_quiet_material_is_left_alone():
    gov = governor()
    cfg = config()
    assert play(gov, cfg, 60.0, section="verse", **QUIET) == []
    assert gov.telemetry.accents == 0


def test_a_build_alone_is_not_an_accent():
    gov = governor()
    cfg = config()
    assert play(gov, cfg, 60.0, section="buildup", **BUILD) == []


# ---------------------------------------------------------------------------
# Anticipation
# ---------------------------------------------------------------------------


def test_an_accent_is_preceded_by_a_cut():
    """The drop needs darkness to land against — *before* it, not during it.

    The dip is armed by the gap at the top of a build, which is the only cue
    available ahead of the hit. Arming it on the frame the accent window opens
    would run the cut from t to t+dip_s and remove light exactly as the drop
    arrives, which is a post-hit cut wearing the name of anticipation.
    """
    gov = governor()
    cfg = config()
    caps = []
    for i in range(int(30.0 * FPS)):
        now = i * DT
        # An intro, a build that tops out, a two-second pre-drop gap, the drop.
        if now < 2.0:
            feats = dict(energy=0.15, bass=0.15)
        elif now < 6.0:
            feats = dict(energy=0.15 + 0.70 * (now - 2.0) / 4.0, bass=0.20)
        elif now < 7.0:
            feats = dict(energy=0.85, bass=0.20)
        elif now < 9.0:
            feats = dict(energy=0.15, bass=0.05)
        else:
            feats = DROP
        # section="verse", so the only thing that can fire an accent here is the
        # drop cue itself rather than sitting inside a section called "drop".
        gov.tick(now=now, delta_time=DT, section="verse", config=cfg, **feats)
        caps.append((now, cfg.audience_intensity_cap, cfg.strobe_enabled))

    assert gov.telemetry.dips >= 1, "no anticipation dip was ever armed"
    first_on = next(t for t, _, on in caps if on)

    # Every dip frame must sit strictly before the accent window opens.
    dipped = [t for t, c, _ in caps if c <= gov.posture.dip_level]
    assert dipped, "the dip never reached its level"
    assert max(dipped) < first_on, (
        f"dip frames run to {max(dipped):.3f}, at or after the accent at {first_on:.3f}"
    )

    # ... and the rig is not being held down once the accent is running.
    during = [c for t, c, _ in caps if first_on <= t < first_on + gov.posture.window_s]
    assert during and min(during) > gov.posture.dip_level


def test_the_build_ramp_releases_as_the_build_climbs():
    gov = governor()
    cfg = config()
    caps = []
    for i in range(int(30.0 * FPS)):
        # Energy climbing over half a minute is a build; the ramp holds the rig
        # back at its foot and lets go at the top.
        energy = 0.10 + 0.55 * (i / (30.0 * FPS))
        gov.tick(now=i * DT, delta_time=DT, section="buildup", config=cfg,
                 energy=energy, bass=0.15)
        caps.append(cfg.audience_intensity_cap)

    assert min(caps) < 0.95, "the build ramp never engaged"
    assert caps[-1] > min(caps) + 0.05, "the build ramp never released"


def test_nothing_is_held_back_when_there_is_no_build():
    gov = governor()
    cfg = config()
    caps = []
    for i in range(int(20.0 * FPS)):
        gov.tick(now=i * DT, delta_time=DT, section="verse", config=cfg,
                 energy=0.40, bass=0.90)
        caps.append(cfg.audience_intensity_cap)
    assert min(caps[int(5.0 * FPS):]) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# It has to survive the 60 fps path
# ---------------------------------------------------------------------------


def test_the_governor_never_raises_on_hostile_input():
    gov = governor()
    cfg = config()
    for now, dt, energy, bass, section in (
        (0.0, float("nan"), 0.5, 0.5, "drop"),
        (1.0, DT, float("nan"), float("inf"), "drop"),
        (2.0, -5.0, -3.0, 12.0, ""),
        (3.0, 1e9, 0.5, 0.5, None),
    ):
        gov.tick(now=now, delta_time=dt, energy=energy, bass=bass,
                 section=section, config=cfg)
        assert 0.0 <= cfg.audience_intensity_cap <= 1.0
        assert isinstance(cfg.strobe_enabled, bool)


def test_a_broken_config_object_does_not_take_the_rig_down():
    class Immovable:
        accessibility_mode = "conservative"
        venue_mode = "concert"
        camera_mode = False
        strobe_hz_cap = 3.0
        strobe_max_duty_cycle = 0.34
        strobe_burst_max_s = 0.1
        strobe_refractory_s = 0.3
        audience_intensity_cap = 1.0

        @property
        def strobe_enabled(self):
            return True

    gov = governor()
    gov.tick(now=0.0, delta_time=DT, section="drop", config=Immovable(), **DROP)
    assert gov.telemetry.faults >= 1


def test_a_clean_run_records_no_faults():
    """`tick` swallows exceptions, so silence has to be distinguishable."""
    gov = governor()
    cfg = config()
    play(gov, cfg, 60.0, section="drop", **DROP)
    play(gov, cfg, 30.0, start=60.0, section="verse", **QUIET)
    assert gov.telemetry.faults == 0


def test_attaching_to_the_engine_governs_the_flag_and_is_idempotent():
    engine = EffectsEngine(EffectsConfig(
        auto_mode=True, strobe_enabled=True, accessibility_mode="conservative",
        strobe_hz_cap=3.0,
    ))
    engine.enable_pro_lighting(True)
    engine.set_genre(Genre.JAZZ)
    gov = attach_accent_governor(engine)
    assert attach_accent_governor(engine) is gov

    engine.update_audio(energy=0.9, bass=0.95, is_beat=True)
    for _ in range(120):
        engine.update(delta_time=DT)

    # Jazz has no budget, so no frame may leave the flag on.
    assert engine.config.strobe_enabled is False
    assert gov.telemetry.faults == 0


# ---------------------------------------------------------------------------
# ProStrobe's own limits
# ---------------------------------------------------------------------------


def test_every_repeating_strobe_mode_is_refused_once_the_budget_is_gone():
    strobe = ProStrobe()
    strobe.set_genre("jazz")
    for mode in (ProStrobeMode.BURST, ProStrobeMode.BLINDER, ProStrobeMode.PROGRESSIVE,
                 ProStrobeMode.CONTINUOUS, ProStrobeMode.CHASE_STROBE):
        strobe.set_mode(mode, frequency=20.0)
        assert strobe.params.mode == ProStrobeMode.OFF, mode


def test_re_asserting_a_continuous_mode_does_not_drain_the_budget():
    strobe = ProStrobe()
    strobe.set_genre("rock")
    for _ in range(500):
        strobe.set_mode(ProStrobeMode.CONTINUOUS, frequency=20.0)
    assert strobe.strobe_budget_remaining == 2


def test_no_mode_can_be_asked_to_flash_faster_than_its_own_limit():
    strobe = ProStrobe()
    strobe.set_mode(ProStrobeMode.CONTINUOUS, frequency=200.0)
    assert strobe.params.frequency <= strobe.params.max_continuous_hz
    strobe.set_mode(ProStrobeMode.CHASE_STROBE, frequency=200.0)
    assert strobe.params.frequency <= strobe.params.max_continuous_hz
    strobe.set_mode(ProStrobeMode.PROGRESSIVE, progressive_end_hz=200.0)
    assert strobe.params.progressive_end_hz <= strobe.params.max_burst_hz
    strobe.set_mode(ProStrobeMode.BURST, burst_frequency=200.0, burst_duration=99.0)
    assert strobe.params.burst_frequency <= strobe.params.max_burst_hz
    assert strobe.params.burst_duration <= strobe.params.max_burst_seconds


# ---------------------------------------------------------------------------
# Durable operator/venue intent
#
# The governor writes `strobe_enabled` and `audience_intensity_cap` on every
# frame, so a read-back comparison cannot see a write that happens to equal the
# value it last wrote itself. These are the cases that slips through.
# ---------------------------------------------------------------------------


def _engine_with_governor(**overrides):
    kwargs = dict(
        auto_mode=True, strobe_enabled=True, accessibility_mode="conservative",
        strobe_hz_cap=3.0, strobe_max_duty_cycle=0.34,
    )
    kwargs.update(overrides)
    engine = EffectsEngine(EffectsConfig(**kwargs))
    engine.enable_pro_lighting(True)
    engine.set_genre(Genre.EDM)
    return engine, attach_accent_governor(engine)


def test_switching_strobe_off_between_accents_is_a_hard_off_switch():
    """The case the read-back comparison structurally cannot see.

    Between accents the governor already holds `strobe_enabled` False, so an
    operator writing False is byte-identical to the governor's own last write.
    `POST /effects/layers/strobe/false` routes through
    `EffectsEngine.set_strobe_layer_enabled`, which tells the governor.
    """
    gov = governor()
    cfg = config()
    assert windows(play(gov, cfg, 20.0, section="drop", **DROP))

    # Land on a frame between accents, where the flag is already False.
    play(gov, cfg, 0.5, start=20.0, section="verse", **QUIET)
    assert cfg.strobe_enabled is False

    cfg.strobe_enabled = False          # the operator's write: a no-op on the field
    gov.set_enabled(False)              # ... and the durable intent alongside it

    assert play(gov, cfg, 60.0, start=30.0, section="drop", **DROP) == []


def test_the_engine_strobe_layer_switch_reaches_the_governor():
    """End to end through the object the endpoint actually calls."""
    engine, gov = _engine_with_governor()
    frame = 0

    def beat_programme(n):
        # A kick pattern: the low end has to *arrive* for the drop cue to fire.
        engine.update_audio(energy=0.9, bass=0.95 if (n // 20) % 2 == 0 else 0.15,
                            is_beat=(n % 20 == 0))

    for _ in range(int(20 * FPS)):
        beat_programme(frame)
        engine.update(delta_time=DT)
        frame += 1
    assert gov.telemetry.accents >= 1

    engine.set_strobe_layer_enabled(False)
    accents_before = gov.telemetry.accents
    armed = 0
    for _ in range(int(30 * FPS)):
        beat_programme(frame)
        engine.update(delta_time=DT)
        frame += 1
        if engine.config.strobe_enabled:
            armed += 1

    assert gov.telemetry.accents == accents_before, "governor fired after the operator's off"
    assert armed == 0, f"governor re-armed strobe on {armed} frames after the operator's off"
    assert gov.telemetry.faults == 0


@pytest.mark.parametrize("governor_cap", [1.0, 0.85, 0.04])
def test_a_venue_tightening_the_audience_cap_is_not_reverted(governor_cap):
    """`set_safety_profile` does `min(cap, 0.90)`.

    When the governor is mid build-ramp (cap 0.85) or mid dip (cap 0.04) that
    min() returns the value the governor itself just wrote, so a read-back
    comparison sees no change and the tightening was silently undone on the
    next frame.
    """
    gov = governor()
    cfg = config()
    play(gov, cfg, 3.0, **BUILD)

    cfg.audience_intensity_cap = governor_cap
    gov._wrote_cap = governor_cap

    tightened = min(cfg.audience_intensity_cap, 0.90)
    cfg.audience_intensity_cap = tightened
    gov.set_nominal_cap(tightened)

    play(gov, cfg, 5.0, start=100.0, **BUILD)
    assert cfg.audience_intensity_cap <= tightened + 1e-6, (
        f"cap drifted back up to {cfg.audience_intensity_cap} from {tightened}"
    )


def test_set_safety_profile_tightening_survives_the_governor():
    """The whole path: engine method, governor attached, several seconds later.

    Staged on the case a read-back comparison cannot see. `set_safety_profile`
    does `min(cap, 0.90)`; when the governor is already holding the cap at 0.90
    (mid build ramp, or mid dip) that min() returns the governor's own last
    written value, so nothing about the config changed and only an explicit
    hand-off can carry the tightening.
    """
    engine, gov = _engine_with_governor(accessibility_mode="performance")
    engine.update_audio(energy=0.9, bass=0.95, is_beat=True)
    for _ in range(int(3 * FPS)):
        engine.update(delta_time=DT)

    # The governor is holding the cap down itself, and its nominal is still 1.0.
    gov._wrote_cap = 0.90
    engine.config.audience_intensity_cap = 0.90
    assert gov._nominal_cap == pytest.approx(1.0)

    applied = engine.set_safety_profile("conservative")["audience_intensity_cap"]
    assert applied == pytest.approx(0.90)

    for _ in range(int(5 * FPS)):
        engine.update(delta_time=DT)

    assert engine.config.audience_intensity_cap <= applied + 1e-6, (
        f"cap drifted back to {engine.config.audience_intensity_cap} after "
        f"set_safety_profile applied {applied}"
    )


def test_manual_mode_leaves_the_strobe_flag_to_the_operator():
    """In manual mode the accent decision is not the governor's to make.

    The governor ticks from the wrapped `engine.update` regardless of mode, so
    without a stand-down it cancels a manual strobe within one frame and the
    non-reactive busking strobe with it.
    """
    engine, gov = _engine_with_governor(auto_mode=False)
    engine.update_audio(energy=0.9, bass=0.95, is_beat=True)
    engine.config.strobe_enabled = True

    for _ in range(int(5 * FPS)):
        engine.update(delta_time=DT)
        assert engine.config.strobe_enabled is True, "governor cancelled a manual strobe"
    assert gov.telemetry.faults == 0


def test_no_dip_is_armed_while_an_accent_is_running():
    """The build gap can re-satisfy itself as the drop recovers."""
    gov = governor()
    cfg = config()
    gov._window_until = 100.0          # an accent is running
    before = gov.telemetry.dips
    gov._arm_dip(50.0)
    assert gov.telemetry.dips == before
    assert gov._dip_until < 50.0
