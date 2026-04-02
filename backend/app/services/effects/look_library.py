"""
Look Library — Mood-Tagged Effect Presets for Non-Repeating Shows
================================================================

A "look" is a complete lighting state recipe:
- Movement pattern (what the movers do)
- Dimmer effect (chase style, bump behavior)
- Color character (warm/cool, saturation, contrast)
- Intensity profile (base dimmer, bump strength)
- Timing (how fast things change)

Looks are tagged by mood, energy level, and compatible sections.
The engine randomly selects from matching looks so the show
is different every time but always fits the musical moment.

Design philosophy:
- Each look is a self-contained "scene" that works on its own
- Multiple looks in the same mood category are visually distinct
- Random selection ensures no two shows look the same
- Mood compatibility ensures the lighting always matches the music
"""

import random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class LookPreset:
    """A complete lighting look preset."""
    name: str                          # human-readable name
    movement_pattern: str              # one of the _symmetric_pan_tilt patterns
    chase_direction: str               # "forward", "bounce", "center_out", "none"
    chase_beats: float                 # chase speed in beats per cycle
    chase_width: float                 # gaussian width of chase spotlight
    chase_intensity: float             # 0-1 how bright the chase peak is
    bump_strength: float               # 0-1 beat bump intensity
    bump_style: str                    # "all", "travel", "downbeat_only"
    base_dimmer: float                 # 0-1 base brightness level
    color_saturation: float            # 0-1 how saturated colors are
    color_contrast: float              # 0-1 how different dominant vs accent
    speed_factor: float                # multiplier on movement speed
    amplitude_factor: float            # multiplier on movement width

    # Compatibility tags
    moods: List[str] = field(default_factory=list)       # which moods this fits
    energy_min: float = 0.0            # minimum energy level
    energy_max: float = 1.0            # maximum energy level
    sections: List[str] = field(default_factory=list)    # compatible sections
    weight: float = 1.0               # selection weight (higher = picked more often)


# ══════════════════════════════════════════════════════════════════════
#  THE LIBRARY — 40+ diverse looks tagged by mood/energy/section
# ══════════════════════════════════════════════════════════════════════

LOOK_LIBRARY: List[LookPreset] = [
    # ────────────────────────────────────────────
    #  ETHEREAL / EMOTIONAL looks (low energy)
    # ────────────────────────────────────────────
    LookPreset(
        name="ethereal_flyout",
        movement_pattern="fly_out", chase_direction="none", chase_beats=8.0,
        chase_width=0.4, chase_intensity=0.0, bump_strength=0.0,
        bump_style="none", base_dimmer=0.20, color_saturation=0.4,
        color_contrast=0.2, speed_factor=0.3, amplitude_factor=1.5,
        moods=["ethereal", "melancholy", "transcendent", "chill"],
        energy_min=0.0, energy_max=0.3,
        sections=["breakdown", "ethereal"],
    ),
    LookPreset(
        name="slow_breathe_deep",
        movement_pattern="slow_breathe", chase_direction="none", chase_beats=16.0,
        chase_width=0.5, chase_intensity=0.0, bump_strength=0.0,
        bump_style="none", base_dimmer=0.15, color_saturation=0.3,
        color_contrast=0.15, speed_factor=0.25, amplitude_factor=1.3,
        moods=["ethereal", "melancholy", "chill", "natural"],
        energy_min=0.0, energy_max=0.25,
        sections=["breakdown", "ethereal"],
    ),
    LookPreset(
        name="audience_glow",
        movement_pattern="audience_scan", chase_direction="center_out", chase_beats=8.0,
        chase_width=0.35, chase_intensity=0.15, bump_strength=0.0,
        bump_style="none", base_dimmer=0.18, color_saturation=0.35,
        color_contrast=0.2, speed_factor=0.35, amplitude_factor=1.2,
        moods=["romantic", "melancholy", "ethereal"],
        energy_min=0.0, energy_max=0.3,
        sections=["breakdown", "verse"],
    ),
    LookPreset(
        name="moonlight_drift",
        movement_pattern="tilt_wave", chase_direction="none", chase_beats=8.0,
        chase_width=0.3, chase_intensity=0.0, bump_strength=0.0,
        bump_style="none", base_dimmer=0.12, color_saturation=0.25,
        color_contrast=0.1, speed_factor=0.2, amplitude_factor=1.0,
        moods=["nocturnal", "melancholy", "ethereal"],
        energy_min=0.0, energy_max=0.2,
        sections=["breakdown", "ethereal"],
    ),

    # ────────────────────────────────────────────
    #  VERSE / MODERATE ENERGY looks
    # ────────────────────────────────────────────
    LookPreset(
        name="mirror_chase_verse",
        movement_pattern="mirror_sweep", chase_direction="forward", chase_beats=4.0,
        chase_width=0.22, chase_intensity=0.35, bump_strength=0.12,
        bump_style="travel", base_dimmer=0.50, color_saturation=0.6,
        color_contrast=0.4, speed_factor=0.75, amplitude_factor=1.0,
        moods=["party", "joyful", "natural"],
        energy_min=0.25, energy_max=0.6,
        sections=["verse"],
    ),
    LookPreset(
        name="symmetric_fan_verse",
        movement_pattern="symmetric_fan", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.25, chase_intensity=0.30, bump_strength=0.10,
        bump_style="travel", base_dimmer=0.48, color_saturation=0.55,
        color_contrast=0.35, speed_factor=0.7, amplitude_factor=0.9,
        moods=["chill", "romantic", "joyful"],
        energy_min=0.2, energy_max=0.55,
        sections=["verse"],
    ),
    LookPreset(
        name="cascade_verse",
        movement_pattern="cascade", chase_direction="center_out", chase_beats=4.0,
        chase_width=0.20, chase_intensity=0.32, bump_strength=0.14,
        bump_style="travel", base_dimmer=0.52, color_saturation=0.6,
        color_contrast=0.45, speed_factor=0.8, amplitude_factor=1.0,
        moods=["natural", "party", "joyful"],
        energy_min=0.3, energy_max=0.65,
        sections=["verse"],
    ),
    LookPreset(
        name="tilt_wave_moody",
        movement_pattern="tilt_wave", chase_direction="forward", chase_beats=4.0,
        chase_width=0.28, chase_intensity=0.28, bump_strength=0.08,
        bump_style="downbeat_only", base_dimmer=0.45, color_saturation=0.5,
        color_contrast=0.3, speed_factor=0.65, amplitude_factor=0.85,
        moods=["melancholy", "nocturnal", "romantic"],
        energy_min=0.2, energy_max=0.5,
        sections=["verse"],
    ),
    LookPreset(
        name="audience_sweep_verse",
        movement_pattern="audience_scan", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.24, chase_intensity=0.25, bump_strength=0.10,
        bump_style="travel", base_dimmer=0.50, color_saturation=0.55,
        color_contrast=0.35, speed_factor=0.7, amplitude_factor=1.1,
        moods=["party", "joyful", "romantic"],
        energy_min=0.25, energy_max=0.6,
        sections=["verse"],
    ),
    LookPreset(
        name="stagger_subtle",
        movement_pattern="stagger_sweep", chase_direction="forward", chase_beats=4.0,
        chase_width=0.22, chase_intensity=0.30, bump_strength=0.12,
        bump_style="travel", base_dimmer=0.48, color_saturation=0.6,
        color_contrast=0.4, speed_factor=0.75, amplitude_factor=0.95,
        moods=["chill", "natural", "joyful"],
        energy_min=0.2, energy_max=0.55,
        sections=["verse"],
    ),

    # ────────────────────────────────────────────
    #  BUILDUP looks (rising energy)
    # ────────────────────────────────────────────
    LookPreset(
        name="circle_buildup",
        movement_pattern="symmetric_circle", chase_direction="forward", chase_beats=2.0,
        chase_width=0.18, chase_intensity=0.45, bump_strength=0.20,
        bump_style="travel", base_dimmer=0.60, color_saturation=0.7,
        color_contrast=0.5, speed_factor=1.0, amplitude_factor=1.0,
        moods=["party", "fiery", "aggressive"],
        energy_min=0.35, energy_max=0.8,
        sections=["buildup"],
    ),
    LookPreset(
        name="cross_tilt_tension",
        movement_pattern="cross_tilt", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.16, chase_intensity=0.48, bump_strength=0.22,
        bump_style="travel", base_dimmer=0.58, color_saturation=0.75,
        color_contrast=0.55, speed_factor=1.1, amplitude_factor=1.05,
        moods=["aggressive", "fiery", "party"],
        energy_min=0.4, energy_max=0.85,
        sections=["buildup"],
    ),
    LookPreset(
        name="mirror_accelerate",
        movement_pattern="mirror_sweep", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.50, bump_strength=0.18,
        bump_style="travel", base_dimmer=0.55, color_saturation=0.65,
        color_contrast=0.45, speed_factor=1.0, amplitude_factor=1.1,
        moods=["party", "joyful", "luxury"],
        energy_min=0.35, energy_max=0.75,
        sections=["buildup"],
    ),
    LookPreset(
        name="stagger_ramp",
        movement_pattern="stagger_sweep", chase_direction="forward", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.52, bump_strength=0.22,
        bump_style="travel", base_dimmer=0.60, color_saturation=0.7,
        color_contrast=0.5, speed_factor=1.05, amplitude_factor=1.0,
        moods=["fiery", "aggressive", "party"],
        energy_min=0.4, energy_max=0.85,
        sections=["buildup"],
    ),

    # ────────────────────────────────────────────
    #  CHORUS looks (high energy, sustained)
    # ────────────────────────────────────────────
    LookPreset(
        name="ballyhoo_full",
        movement_pattern="ballyhoo", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.50, bump_strength=0.28,
        bump_style="travel", base_dimmer=0.80, color_saturation=0.85,
        color_contrast=0.6, speed_factor=1.0, amplitude_factor=1.0,
        moods=["party", "joyful", "luxury"],
        energy_min=0.5, energy_max=1.0,
        sections=["chorus"],
    ),
    LookPreset(
        name="symmetric_circle_chorus",
        movement_pattern="symmetric_circle", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.48, bump_strength=0.25,
        bump_style="travel", base_dimmer=0.78, color_saturation=0.8,
        color_contrast=0.55, speed_factor=1.0, amplitude_factor=1.1,
        moods=["party", "romantic", "joyful"],
        energy_min=0.45, energy_max=1.0,
        sections=["chorus"],
    ),
    LookPreset(
        name="figure8_wide_chorus",
        movement_pattern="figure_eight_wide", chase_direction="forward", chase_beats=2.0,
        chase_width=0.16, chase_intensity=0.45, bump_strength=0.22,
        bump_style="travel", base_dimmer=0.82, color_saturation=0.8,
        color_contrast=0.5, speed_factor=0.95, amplitude_factor=1.15,
        moods=["romantic", "joyful", "ethereal"],
        energy_min=0.4, energy_max=0.9,
        sections=["chorus"],
    ),
    LookPreset(
        name="cascade_chorus",
        movement_pattern="cascade", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.50, bump_strength=0.25,
        bump_style="travel", base_dimmer=0.80, color_saturation=0.85,
        color_contrast=0.6, speed_factor=1.0, amplitude_factor=1.0,
        moods=["natural", "party", "fiery"],
        energy_min=0.5, energy_max=1.0,
        sections=["chorus"],
    ),
    LookPreset(
        name="mirror_fan_chorus",
        movement_pattern="mirror_sweep", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.12, chase_intensity=0.52, bump_strength=0.30,
        bump_style="travel", base_dimmer=0.85, color_saturation=0.9,
        color_contrast=0.65, speed_factor=1.05, amplitude_factor=1.0,
        moods=["aggressive", "fiery", "party"],
        energy_min=0.55, energy_max=1.0,
        sections=["chorus"],
    ),
    LookPreset(
        name="snap_look_chorus",
        movement_pattern="snap_look", chase_direction="bounce", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55, bump_strength=0.30,
        bump_style="all", base_dimmer=0.82, color_saturation=0.85,
        color_contrast=0.6, speed_factor=1.0, amplitude_factor=1.0,
        moods=["aggressive", "party", "luxury"],
        energy_min=0.55, energy_max=1.0,
        sections=["chorus"],
    ),
    LookPreset(
        name="stagger_chorus",
        movement_pattern="stagger_sweep", chase_direction="forward", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.50, bump_strength=0.25,
        bump_style="travel", base_dimmer=0.80, color_saturation=0.8,
        color_contrast=0.55, speed_factor=1.0, amplitude_factor=1.0,
        moods=["party", "joyful", "natural"],
        energy_min=0.45, energy_max=1.0,
        sections=["chorus"],
    ),

    # ────────────────────────────────────────────
    #  DROP looks (maximum energy)
    # ────────────────────────────────────────────
    LookPreset(
        name="center_burst_drop",
        movement_pattern="center_burst", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55, bump_strength=0.40,
        bump_style="all", base_dimmer=0.95, color_saturation=1.0,
        color_contrast=0.7, speed_factor=1.2, amplitude_factor=1.0,
        moods=["party", "fiery", "aggressive"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
    ),
    LookPreset(
        name="ballyhoo_drop",
        movement_pattern="ballyhoo", chase_direction="forward", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.58, bump_strength=0.38,
        bump_style="travel", base_dimmer=0.95, color_saturation=0.95,
        color_contrast=0.65, speed_factor=1.25, amplitude_factor=1.1,
        moods=["party", "joyful", "luxury"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
    ),
    LookPreset(
        name="sync_sweep_drop",
        movement_pattern="sync_sweep", chase_direction="bounce", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.55, bump_strength=0.35,
        bump_style="travel", base_dimmer=0.92, color_saturation=1.0,
        color_contrast=0.6, speed_factor=1.15, amplitude_factor=1.0,
        moods=["fiery", "aggressive", "party"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
    ),
    LookPreset(
        name="stagger_drop",
        movement_pattern="stagger_sweep", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.55, bump_strength=0.40,
        bump_style="travel", base_dimmer=0.95, color_saturation=1.0,
        color_contrast=0.7, speed_factor=1.2, amplitude_factor=1.0,
        moods=["aggressive", "party", "fiery"],
        energy_min=0.65, energy_max=1.0,
        sections=["drop"],
    ),
    LookPreset(
        name="snap_burst_drop",
        movement_pattern="snap_look", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.58, bump_strength=0.42,
        bump_style="all", base_dimmer=0.95, color_saturation=1.0,
        color_contrast=0.7, speed_factor=1.2, amplitude_factor=1.0,
        moods=["aggressive", "fiery", "party"],
        energy_min=0.7, energy_max=1.0,
        sections=["drop"],
    ),

    # ────────────────────────────────────────────
    #  MOOD-SPECIFIC SPECIALTY looks
    # ────────────────────────────────────────────
    LookPreset(
        name="romantic_waltz",
        movement_pattern="figure_eight_wide", chase_direction="none", chase_beats=8.0,
        chase_width=0.3, chase_intensity=0.0, bump_strength=0.05,
        bump_style="downbeat_only", base_dimmer=0.45, color_saturation=0.5,
        color_contrast=0.3, speed_factor=0.5, amplitude_factor=1.2,
        moods=["romantic", "melancholy"],
        energy_min=0.15, energy_max=0.5,
        sections=["verse", "breakdown"],
    ),
    LookPreset(
        name="nocturnal_slow",
        movement_pattern="slow_breathe", chase_direction="forward", chase_beats=8.0,
        chase_width=0.3, chase_intensity=0.15, bump_strength=0.0,
        bump_style="none", base_dimmer=0.20, color_saturation=0.35,
        color_contrast=0.2, speed_factor=0.3, amplitude_factor=1.0,
        moods=["nocturnal", "melancholy", "ethereal"],
        energy_min=0.0, energy_max=0.3,
        sections=["breakdown", "verse"],
    ),
    LookPreset(
        name="luxury_shimmer",
        movement_pattern="cascade", chase_direction="center_out", chase_beats=4.0,
        chase_width=0.18, chase_intensity=0.40, bump_strength=0.15,
        bump_style="travel", base_dimmer=0.55, color_saturation=0.7,
        color_contrast=0.5, speed_factor=0.8, amplitude_factor=1.0,
        moods=["luxury", "joyful"],
        energy_min=0.3, energy_max=0.7,
        sections=["verse", "chorus"],
    ),
    LookPreset(
        name="feminine_soft",
        movement_pattern="tilt_wave", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.25, chase_intensity=0.30, bump_strength=0.10,
        bump_style="travel", base_dimmer=0.50, color_saturation=0.6,
        color_contrast=0.35, speed_factor=0.7, amplitude_factor=1.0,
        moods=["feminine", "romantic", "joyful"],
        energy_min=0.2, energy_max=0.6,
        sections=["verse", "chorus"],
    ),
    LookPreset(
        name="spiritual_ascend",
        movement_pattern="fly_out", chase_direction="center_out", chase_beats=8.0,
        chase_width=0.30, chase_intensity=0.20, bump_strength=0.05,
        bump_style="downbeat_only", base_dimmer=0.35, color_saturation=0.4,
        color_contrast=0.25, speed_factor=0.35, amplitude_factor=1.4,
        moods=["transcendent", "ethereal", "natural"],
        energy_min=0.1, energy_max=0.5,
        sections=["breakdown", "verse"],
    ),
]


class LookSelector:
    """Selects looks from the library based on current mood/energy/section.

    Uses weighted random selection to ensure variety while maintaining
    mood compatibility. Holds a look for at least 8 bars before changing.
    """

    def __init__(self):
        self._current_look: Optional[LookPreset] = None
        self._look_hold_until_bar: int = 0
        self._look_history: list = []  # last N looks (avoid immediate repeats)
        self._history_size: int = 4
        self._rng = random.Random()  # deterministic within a session
        self._rng.seed(42)           # seed changes each session in practice

    def select_look(self, section: str, energy: float, mood: str,
                    bar_clock: int, force_new: bool = False) -> Optional[LookPreset]:
        """Select a look from the library matching current criteria.

        Args:
            section: Current section (breakdown/verse/buildup/chorus/drop)
            energy: Current energy level (0-1)
            mood: Current mood from lyric theme or default
            bar_clock: Current bar number (for hold timing)
            force_new: Force selection of a new look (e.g. on section change)

        Returns:
            LookPreset if a new look was selected, None if holding current look
        """
        # Check hold timer
        if not force_new and self._current_look is not None:
            if bar_clock < self._look_hold_until_bar:
                return None  # hold current look

        # Find all compatible looks
        candidates = []
        for look in LOOK_LIBRARY:
            # Must match section
            if section not in look.sections:
                continue
            # Must be in energy range
            if energy < look.energy_min or energy > look.energy_max:
                continue
            # Mood match is preferred but not required
            mood_match = mood in look.moods if mood else False

            # Skip if recently used (avoid repeats)
            if look.name in self._look_history:
                continue

            # Weight: mood match gets 3x bonus
            weight = look.weight * (3.0 if mood_match else 1.0)
            candidates.append((look, weight))

        if not candidates:
            # Fallback: relax mood constraint
            for look in LOOK_LIBRARY:
                if section in look.sections and look.energy_min <= energy <= look.energy_max:
                    if look.name not in self._look_history:
                        candidates.append((look, look.weight))

        if not candidates:
            # Ultra-fallback: any look for this section
            for look in LOOK_LIBRARY:
                if section in look.sections:
                    candidates.append((look, look.weight))

        if not candidates:
            return None

        # Weighted random selection
        total_weight = sum(w for _, w in candidates)
        r = self._rng.random() * total_weight
        cumulative = 0.0
        selected = candidates[0][0]
        for look, weight in candidates:
            cumulative += weight
            if r <= cumulative:
                selected = look
                break

        # Update state
        self._current_look = selected
        self._look_hold_until_bar = bar_clock + 8  # hold for 8 bars
        self._look_history.append(selected.name)
        if len(self._look_history) > self._history_size:
            self._look_history.pop(0)

        return selected

    @property
    def current(self) -> Optional[LookPreset]:
        return self._current_look
