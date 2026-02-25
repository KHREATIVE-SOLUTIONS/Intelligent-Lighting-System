"""Pattern library for beam behaviors and focus-aware movement presets."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set

from .movement_patterns import FixtureGrouping, ProMovementParams, ProMovementPattern


class BeamPatternName(Enum):
    """High-level beam pattern families used by scene choreography."""

    FAN = "fan"
    CROSSING_SWEEPS = "crossing_sweeps"
    MIRRORED_PAIRS = "mirrored_pairs"
    CIRCLES = "circles"
    AUDIENCE_SWEEP = "audience_sweep"
    CENTER_FOCUS_HOLD = "center_focus_hold"


class SymmetryMode(Enum):
    """Symmetry behavior for fixture groups."""

    NONE = "none"
    LEFT_RIGHT_MIRROR = "left_right_mirror"
    ALTERNATING_PARITY = "alternating_parity"


@dataclass(frozen=True)
class FocusPointAnchor:
    """Named stage focus point with dwell timing guidance."""

    name: str
    pan_norm: float
    tilt_norm: float
    dwell_beats: float


@dataclass(frozen=True)
class BeamPatternDefinition:
    """Declarative beam pattern setup for ProMovementEngine."""

    movement_pattern: ProMovementPattern
    beat_divisor: float
    pan_amplitude: float
    tilt_amplitude: float
    phase_spread: float
    grouping: FixtureGrouping
    smoothing: float
    default_symmetry: SymmetryMode = SymmetryMode.NONE


FOCUS_POINT_ANCHORS: Dict[str, FocusPointAnchor] = {
    "center_stage": FocusPointAnchor("center_stage", pan_norm=0.0, tilt_norm=-0.20, dwell_beats=2.0),
    "vocalist": FocusPointAnchor("vocalist", pan_norm=-0.12, tilt_norm=-0.12, dwell_beats=3.0),
    "drummer": FocusPointAnchor("drummer", pan_norm=0.18, tilt_norm=-0.28, dwell_beats=4.0),
}


BEAM_PATTERN_LIBRARY: Dict[BeamPatternName, BeamPatternDefinition] = {
    BeamPatternName.FAN: BeamPatternDefinition(
        movement_pattern=ProMovementPattern.VERTICAL_FAN,
        beat_divisor=0.5,
        pan_amplitude=38.0,
        tilt_amplitude=52.0,
        phase_spread=1.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.22,
        default_symmetry=SymmetryMode.ALTERNATING_PARITY,
    ),
    BeamPatternName.CROSSING_SWEEPS: BeamPatternDefinition(
        movement_pattern=ProMovementPattern.SPLIT_SWEEP,
        beat_divisor=0.5,
        pan_amplitude=64.0,
        tilt_amplitude=28.0,
        phase_spread=0.9,
        grouping=FixtureGrouping.LEFT_RIGHT,
        smoothing=0.24,
        default_symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
    ),
    BeamPatternName.MIRRORED_PAIRS: BeamPatternDefinition(
        movement_pattern=ProMovementPattern.MIRROR_SWEEP,
        beat_divisor=0.5,
        pan_amplitude=56.0,
        tilt_amplitude=22.0,
        phase_spread=0.85,
        grouping=FixtureGrouping.PAIRS,
        smoothing=0.20,
        default_symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
    ),
    BeamPatternName.CIRCLES: BeamPatternDefinition(
        movement_pattern=ProMovementPattern.TRUE_CIRCLE,
        beat_divisor=0.25,
        pan_amplitude=58.0,
        tilt_amplitude=42.0,
        phase_spread=0.95,
        grouping=FixtureGrouping.ALL,
        smoothing=0.20,
        default_symmetry=SymmetryMode.ALTERNATING_PARITY,
    ),
    BeamPatternName.AUDIENCE_SWEEP: BeamPatternDefinition(
        movement_pattern=ProMovementPattern.HORIZONTAL_SWEEP,
        beat_divisor=0.5,
        pan_amplitude=82.0,
        tilt_amplitude=18.0,
        phase_spread=0.70,
        grouping=FixtureGrouping.ALL,
        smoothing=0.26,
        default_symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
    ),
    BeamPatternName.CENTER_FOCUS_HOLD: BeamPatternDefinition(
        movement_pattern=ProMovementPattern.SNAP_HOLD,
        beat_divisor=0.33,
        pan_amplitude=70.0,
        tilt_amplitude=45.0,
        phase_spread=0.0,
        grouping=FixtureGrouping.ALL,
        smoothing=0.75,
        default_symmetry=SymmetryMode.NONE,
    ),
}


_ALLOWED_TRANSITIONS: Dict[BeamPatternName, Set[BeamPatternName]] = {
    BeamPatternName.FAN: {
        BeamPatternName.MIRRORED_PAIRS,
        BeamPatternName.CROSSING_SWEEPS,
        BeamPatternName.CENTER_FOCUS_HOLD,
    },
    BeamPatternName.CROSSING_SWEEPS: {
        BeamPatternName.FAN,
        BeamPatternName.CIRCLES,
        BeamPatternName.AUDIENCE_SWEEP,
    },
    BeamPatternName.MIRRORED_PAIRS: {
        BeamPatternName.FAN,
        BeamPatternName.CENTER_FOCUS_HOLD,
        BeamPatternName.CROSSING_SWEEPS,
    },
    BeamPatternName.CIRCLES: {
        BeamPatternName.CROSSING_SWEEPS,
        BeamPatternName.AUDIENCE_SWEEP,
        BeamPatternName.CENTER_FOCUS_HOLD,
    },
    BeamPatternName.AUDIENCE_SWEEP: {
        BeamPatternName.CROSSING_SWEEPS,
        BeamPatternName.CIRCLES,
        BeamPatternName.CENTER_FOCUS_HOLD,
    },
    BeamPatternName.CENTER_FOCUS_HOLD: {
        BeamPatternName.FAN,
        BeamPatternName.MIRRORED_PAIRS,
        BeamPatternName.CROSSING_SWEEPS,
    },
}


def allowed_transitions() -> Dict[BeamPatternName, Set[BeamPatternName]]:
    """Return allowed transition map between beam patterns."""
    return _ALLOWED_TRANSITIONS


def _resolve_grouping(symmetry_mode: SymmetryMode, fallback: FixtureGrouping) -> FixtureGrouping:
    if symmetry_mode == SymmetryMode.LEFT_RIGHT_MIRROR:
        return FixtureGrouping.LEFT_RIGHT
    if symmetry_mode == SymmetryMode.ALTERNATING_PARITY:
        return FixtureGrouping.ODD_EVEN
    return fallback


def build_pattern_params(
    pattern_name: BeamPatternName,
    symmetry_mode: Optional[SymmetryMode] = None,
    focus_anchor: Optional[FocusPointAnchor] = None,
    amplitude_scale: float = 1.0,
) -> ProMovementParams:
    """Build ProMovementParams for a beam pattern and optional anchor/symmetry modifiers."""
    definition = BEAM_PATTERN_LIBRARY[pattern_name]
    resolved_symmetry = symmetry_mode or definition.default_symmetry

    pan_amp = max(5.0, definition.pan_amplitude * amplitude_scale)
    tilt_amp = max(0.0, definition.tilt_amplitude * amplitude_scale)

    params = ProMovementParams(
        pattern=definition.movement_pattern,
        beat_divisor=definition.beat_divisor,
        pan_amplitude=pan_amp,
        tilt_amplitude=tilt_amp,
        phase_spread=definition.phase_spread,
        grouping=_resolve_grouping(resolved_symmetry, definition.grouping),
        smoothing=definition.smoothing,
    )

    if pattern_name == BeamPatternName.CENTER_FOCUS_HOLD:
        anchor = focus_anchor or FOCUS_POINT_ANCHORS["center_stage"]
        dwell = max(1.0, float(anchor.dwell_beats))
        params.beat_divisor = 1.0 / dwell
        # Hold around anchor, with occasional side offsets to avoid dead static look.
        params.snap_positions = [
            (anchor.pan_norm, anchor.tilt_norm),
            (anchor.pan_norm - 0.22, anchor.tilt_norm + 0.10),
            (anchor.pan_norm + 0.22, anchor.tilt_norm + 0.10),
        ]

    return params
