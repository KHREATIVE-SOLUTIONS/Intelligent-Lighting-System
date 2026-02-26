from app.services.lighting.beam_pattern_library import (
    BeamPatternName,
    FOCUS_POINT_ANCHORS,
    SymmetryMode,
    allowed_transitions,
    build_pattern_params,
)
from app.services.lighting.beam_scene_state_machine import BeamSceneStateMachine, ScenePhase
from app.services.lighting.beam_look_scheduler import BeamLookScheduler
from app.services.lighting.movement_patterns import FixtureGrouping, ProMovementPattern


def test_pattern_library_maps_requested_behaviors_and_symmetry_modes():
    fan = build_pattern_params(BeamPatternName.FAN, symmetry_mode=SymmetryMode.ALTERNATING_PARITY)
    crossing = build_pattern_params(
        BeamPatternName.CROSSING_SWEEPS, symmetry_mode=SymmetryMode.LEFT_RIGHT_MIRROR
    )
    circles = build_pattern_params(BeamPatternName.CIRCLES)
    audience = build_pattern_params(BeamPatternName.AUDIENCE_SWEEP)

    assert fan.pattern == ProMovementPattern.VERTICAL_FAN
    assert fan.grouping == FixtureGrouping.ODD_EVEN
    assert crossing.pattern == ProMovementPattern.SPLIT_SWEEP
    assert crossing.grouping == FixtureGrouping.LEFT_RIGHT
    assert circles.pattern == ProMovementPattern.TRUE_CIRCLE
    assert audience.pan_amplitude > circles.pan_amplitude


def test_center_focus_hold_uses_anchor_and_dwell_time():
    vocalist = FOCUS_POINT_ANCHORS["vocalist"]
    focus_params = build_pattern_params(
        BeamPatternName.CENTER_FOCUS_HOLD,
        focus_anchor=vocalist,
    )

    assert focus_params.pattern == ProMovementPattern.SNAP_HOLD
    assert focus_params.beat_divisor == 1.0 / vocalist.dwell_beats
    assert focus_params.snap_positions
    assert focus_params.snap_positions[0] == (vocalist.pan_norm, vocalist.tilt_norm)


def test_scene_state_machine_enforces_allowed_transitions_and_cooldowns():
    machine = BeamSceneStateMachine(initial_pattern=BeamPatternName.FAN)

    # Finish enter stage.
    machine.update(1.0)
    assert machine.current_pattern == BeamPatternName.FAN

    # Disallowed direct transition should be rejected.
    assert not machine.request_transition(BeamPatternName.AUDIENCE_SWEEP)

    # Allowed transition to crossing sweeps.
    assert BeamPatternName.CROSSING_SWEEPS in allowed_transitions()[BeamPatternName.FAN]
    assert machine.request_transition(BeamPatternName.CROSSING_SWEEPS)

    # Complete exit + enter into target pattern.
    machine.update(0.6)
    output = machine.update(0.7)
    assert machine.current_pattern == BeamPatternName.CROSSING_SWEEPS
    assert output.phase in {ScenePhase.ENTER, ScenePhase.HOLD}

    # Immediate back-transition should be blocked by cooldown.
    assert not machine.request_transition(BeamPatternName.FAN)


def test_beam_look_scheduler_uses_section_and_energy_with_hold_constraints(monkeypatch):
    scheduler = BeamLookScheduler()

    timeline = iter([0.0, 0.5, 8.0, 9.0, 30.0])
    monkeypatch.setattr("app.services.lighting.beam_look_scheduler.time.time", lambda: next(timeline))

    intro = scheduler.select_look(section="intro", energy=0.2, bpm=120.0, bars_elapsed=0)
    quick_change_blocked = scheduler.select_look(section="drop", energy=0.95, bpm=128.0, bars_elapsed=1)
    section_change_allowed = scheduler.select_look(section="drop", energy=0.95, bpm=128.0, bars_elapsed=8)
    cooldown_blocks = scheduler.select_look(section="chorus", energy=0.8, bpm=128.0, bars_elapsed=9)
    low_energy_rotation = scheduler.select_look(section="verse", energy=0.2, bpm=120.0, bars_elapsed=30)

    assert intro.name in {"center_punch", "fan", "opposing_sweeps"}
    assert quick_change_blocked.name == intro.name
    assert section_change_allowed.name in {"audience_sweeps", "crisscross"}
    assert cooldown_blocks.name == section_change_allowed.name
    assert low_energy_rotation.name in {"center_punch", "fan", "opposing_sweeps"}


def test_beam_look_scheduler_bar_rotation_prefers_8_or_16_bar_boundaries(monkeypatch):
    scheduler = BeamLookScheduler()

    timeline = iter([0.0, 20.0, 21.0])
    monkeypatch.setattr("app.services.lighting.beam_look_scheduler.time.time", lambda: next(timeline))

    first = scheduler.select_look(section="verse", energy=0.3, bpm=120.0, bars_elapsed=0)
    # Low energy -> 16-bar cadence, so 8 bars should not rotate.
    same = scheduler.select_look(section="verse", energy=0.3, bpm=120.0, bars_elapsed=8)
    # At 16+ bars, rotation is allowed.
    rotated = scheduler.select_look(section="verse", energy=0.3, bpm=120.0, bars_elapsed=17)

    assert same.name == first.name
    assert rotated.name in {"center_punch", "fan", "opposing_sweeps"}
