"""Section-aware beam look scheduler for choreography scene selection."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .beam_pattern_library import BeamPatternName, FOCUS_POINT_ANCHORS, SymmetryMode


@dataclass(frozen=True)
class BeamLook:
    """Full look bundle so one scheduler decision drives multiple parameters together."""

    name: str
    pattern: BeamPatternName
    symmetry: SymmetryMode
    focus_anchor_name: str
    intensity_scale: float
    strobe_mode: str
    strobe_frequency_hz: float
    strobe_intensity: float
    zoom: float
    speed_multiplier: float


BEAM_LOOK_LIBRARY: Dict[str, BeamLook] = {
    "fan": BeamLook(
        name="fan",
        pattern=BeamPatternName.FAN,
        symmetry=SymmetryMode.ALTERNATING_PARITY,
        focus_anchor_name="vocalist",
        intensity_scale=0.86,
        strobe_mode="off",
        strobe_frequency_hz=0.0,
        strobe_intensity=0.0,
        zoom=0.38,
        speed_multiplier=0.85,
    ),
    "crisscross": BeamLook(
        name="crisscross",
        pattern=BeamPatternName.CROSSING_SWEEPS,
        symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
        focus_anchor_name="center_stage",
        intensity_scale=0.95,
        strobe_mode="beat_locked",
        strobe_frequency_hz=0.0,
        strobe_intensity=0.40,
        zoom=0.55,
        speed_multiplier=1.15,
    ),
    "opposing_sweeps": BeamLook(
        name="opposing_sweeps",
        pattern=BeamPatternName.MIRRORED_PAIRS,
        symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
        focus_anchor_name="drummer",
        intensity_scale=0.88,
        strobe_mode="off",
        strobe_frequency_hz=0.0,
        strobe_intensity=0.0,
        zoom=0.44,
        speed_multiplier=0.95,
    ),
    "audience_sweeps": BeamLook(
        name="audience_sweeps",
        pattern=BeamPatternName.AUDIENCE_SWEEP,
        symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
        focus_anchor_name="center_stage",
        intensity_scale=1.0,
        strobe_mode="continuous",
        strobe_frequency_hz=3.2,
        strobe_intensity=0.65,
        zoom=0.78,
        speed_multiplier=1.25,
    ),
    "center_punch": BeamLook(
        name="center_punch",
        pattern=BeamPatternName.CENTER_FOCUS_HOLD,
        symmetry=SymmetryMode.LEFT_RIGHT_MIRROR,
        focus_anchor_name="center_stage",
        intensity_scale=0.72,
        strobe_mode="off",
        strobe_frequency_hz=0.0,
        strobe_intensity=0.0,
        zoom=0.26,
        speed_multiplier=0.7,
    ),
}

# Above this energy a look may strobe; below it the rig stays steady regardless of
# which section the detector reports, so quiet passages never flash.
LOW_ENERGY_MAX = 0.38


class BeamLookScheduler:
    """Bar/section/energy aware scheduler with hold and cooldown constraints."""

    def __init__(self):
        self._rng = random.Random(42)
        self._active_look: BeamLook = BEAM_LOOK_LIBRARY["opposing_sweeps"]
        self._last_switch_time = 0.0
        self._last_switch_bar = 0
        self._cooldown_until = 0.0
        self._last_section = "unknown"

        self._minimum_hold_s = 6.0
        self._transition_cooldown_s = 2.5

    @property
    def active_look(self) -> BeamLook:
        return self._active_look

    def select_look(
        self,
        *,
        section: str,
        energy: float,
        bpm: float,
        bars_elapsed: int,
    ) -> BeamLook:
        """Pick a look every 8/16 bars or immediately on section change."""
        now = time.time()
        section_key = (section or "unknown").lower()
        current_bar = max(0, int(bars_elapsed or 0))
        section_changed = section_key != self._last_section

        bars_per_rotation = 8 if energy >= 0.62 else 16
        bars_since_switch = max(0, current_bar - self._last_switch_bar)
        time_since_switch = now - self._last_switch_time

        should_rotate = bars_since_switch >= bars_per_rotation
        can_switch = time_since_switch >= self._minimum_hold_s and now >= self._cooldown_until
        if section_changed:
            can_switch = now >= self._cooldown_until

        if can_switch and (should_rotate or section_changed):
            next_look = self._choose_candidate(section_key, energy)
            if next_look.name != self._active_look.name:
                self._active_look = next_look
                self._last_switch_time = now
                self._last_switch_bar = current_bar
                beat_sec = 60.0 / max(40.0, float(bpm or 120.0))
                self._cooldown_until = now + max(self._transition_cooldown_s, beat_sec * 4.0)

        self._last_section = section_key
        return self._active_look

    def _choose_candidate(self, section: str, energy: float) -> BeamLook:
        """Energy-aware look selection with section bias."""
        high_energy = ["audience_sweeps", "crisscross"]
        medium_energy = ["fan", "opposing_sweeps", "crisscross"]
        low_energy = ["fan", "opposing_sweeps", "center_punch"]

        if section in {"intro", "outro", "breakdown"}:
            pool = ["fan", "opposing_sweeps", "center_punch"]
        elif section in {"drop", "peak"}:
            pool = ["audience_sweeps", "crisscross"]
        elif section in {"chorus", "buildup", "pre_chorus"}:
            pool = ["crisscross", "fan", "audience_sweeps"]
        elif section in {"verse", "bridge"}:
            pool = ["opposing_sweeps", "fan", "crisscross"]
        elif energy >= 0.72:
            pool = high_energy
        elif energy <= LOW_ENERGY_MAX:
            pool = low_energy
        else:
            pool = medium_energy

        if energy <= LOW_ENERGY_MAX:
            steady = [n for n in pool if BEAM_LOOK_LIBRARY[n].strobe_mode == "off"]
            pool = steady or low_energy

        # Avoid selecting current look when alternatives exist.
        alternatives = [name for name in pool if name != self._active_look.name]
        chosen = self._rng.choice(alternatives or pool)
        return BEAM_LOOK_LIBRARY[chosen]

    def resolve_focus_anchor(self):
        return FOCUS_POINT_ANCHORS[self._active_look.focus_anchor_name]
