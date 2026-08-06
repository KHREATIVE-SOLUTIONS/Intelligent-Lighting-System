"""
Look Library — The Core Decision Engine for Intelligent Lighting
================================================================

A "look" is a COMPLETE lighting recipe that controls EVERYTHING:
- Movement pattern (what the movers do)
- Dimmer effect type (chase, odd/even, circular, ramp, none)
- Strobe behavior (none, beat_pulse, eighth_note, fast_synth, buildup_accel)
- Bump behavior (traveling, all-at-once, downbeat, none)
- Color character (warm/cool, saturation, contrast)
- Intensity profile (base dimmer, bump strength)
- Timing (speed, chase rate)

THE PHILOSOPHY:
Instead of hard-coded rules like "drops always get strobes" or "buildups
always accelerate chases," EVERYTHING is driven by look selection.

Looks are tagged with:
- mood: emotional character (aggressive, euphoric, chill, etc.)
- sections: which song sections this look fits
- energy range: min/max energy level
- audio_character: what the audio SOUNDS like (fast_transients, heavy_bass,
  synth_lead, sparse_ambient, drum_breakdown, etc.)

The selector picks randomly from matching looks, so:
- Fast synth → might get strobe, OR fast chase, OR fast movement
- Drum breakdown → might get traveling bumps, OR odd/even, OR fast chase
- Same song section can look totally different each time
- But it always FITS because the tags ensure mood/energy compatibility

This is what makes each show unique but never wrong.
"""

import random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set, Dict


@dataclass
class LookPreset:
    """A complete lighting look preset — controls ALL behavior."""
    name: str                          # human-readable name

    # ── Movement ──
    movement_pattern: str              # one of the _symmetric_pan_tilt patterns
    speed_factor: float                # multiplier on movement speed
    amplitude_factor: float            # multiplier on movement width

    # ── Dimmer effect ──
    dimmer_effect: str                 # "chase", "odd_even", "circular", "ramp", "none"
    chase_direction: str               # "forward", "bounce", "center_out", "none"
    chase_beats: float                 # chase speed in beats per cycle
    chase_width: float                 # gaussian width of chase spotlight
    chase_intensity: float             # 0-1 how bright the chase peak is

    # ── Bump behavior ──
    bump_strength: float               # 0-1 beat bump intensity
    bump_style: str                    # "all", "travel", "downbeat_only", "none"

    # ── Strobe behavior ──
    strobe_mode: str = "none"          # "none", "beat_pulse", "eighth_note",
                                       # "fast_synth", "buildup_accel", "random_burst"

    # ── Intensity ──
    base_dimmer: float = 0.50          # 0-1 base brightness level
    blinder_mode: str = "none"         # "none", "beat_slam", "downbeat", "pulse"

    # ── Color ──
    color_saturation: float = 0.7      # 0-1 how saturated colors are
    color_contrast: float = 0.5        # 0-1 how different dominant vs accent

    # ── Compatibility tags ──
    moods: List[str] = field(default_factory=list)
    energy_min: float = 0.0
    energy_max: float = 1.0
    sections: List[str] = field(default_factory=list)
    audio_characters: List[str] = field(default_factory=list)  # what the audio sounds like
    weight: float = 1.0

    # ── Musical fingerprint ranges (continuous 0-1 dimensions) ──
    # Each is a (min, max) range. The look selector computes distance
    # from current fingerprint to these ranges — closer = better match.
    # None = don't care about this dimension (always matches).
    dominant_elements: List[str] = field(default_factory=list)  # e.g. ["bass_synth", "drums"]
    activity_range: Optional[Tuple[float, float]] = None        # (min, max) element activity
    density_range: Optional[Tuple[float, float]] = None         # (min, max) mix density
    ambiance_range: Optional[Tuple[float, float]] = None        # (min, max) ambiance/space
    drive_range: Optional[Tuple[float, float]] = None           # (min, max) groove drive
    texture_labels: List[str] = field(default_factory=list)     # e.g. ["percussive", "driving"]

    # ── Fixture group isolation ──
    # Which fixture groups are LIT during this look. Empty = all groups active.
    # Groups: "beam", "wash", "mover", "bar", "strobe", "blinder", "spot"
    # Fixtures NOT in the active groups get dimmed to near-zero (isolated).
    # This enables dark moments where only beams cut through, or only
    # washes fill the room, creating dramatic contrast and focus.
    active_groups: List[str] = field(default_factory=list)  # empty = all active
    # How dark isolated (non-active) fixtures get. 0.0 = full blackout, 0.1 = barely visible.
    isolation_floor: float = 0.03


# ══════════════════════════════════════════════════════════════════════
#  AUDIO CHARACTER DEFINITIONS (for reference)
# ══════════════════════════════════════════════════════════════════════
# "fast_transients"  — rapid synth stabs, arps, fast hi-hats
# "heavy_bass"       — deep sub bass, bass-heavy drops
# "synth_lead"       — prominent melodic synth line
# "drum_breakdown"   — stripped-back drums, rhythmic focus
# "sparse_ambient"   — minimal elements, pads, atmosphere
# "noise_riser"      — white noise/spectral build
# "vocal_heavy"      — prominent vocals
# "percussive"       — lots of percussive elements
# "filtered"         — filter sweep active (muffled or opening)
# "impact"           — big hits, drops landing
# "full_wall"        — everything playing, maximum density


# ══════════════════════════════════════════════════════════════════════
#  THE LIBRARY
# ══════════════════════════════════════════════════════════════════════

LOOK_LIBRARY: List[LookPreset] = [

    # ════════════════════════════════════════════════════════════════
    #  ETHEREAL / BREAKDOWN (low energy, atmospheric)
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="ethereal_flyout",
        movement_pattern="fly_out", speed_factor=0.3, amplitude_factor=1.5,
        dimmer_effect="static", chase_direction="none", chase_beats=8.0,
        chase_width=0.4, chase_intensity=0.0,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.20, color_saturation=0.4, color_contrast=0.2,
        moods=["ethereal", "chill", "ambient"],
        energy_min=0.0, energy_max=0.3,
        sections=["breakdown", "ethereal"],
        audio_characters=["sparse_ambient", "filtered"],
        dominant_elements=["pad", "noise"],
        activity_range=(0.0, 0.3), density_range=(0.0, 0.3),
        ambiance_range=(0.5, 1.0), drive_range=(0.0, 0.2),
        texture_labels=["ambient", "noisy"],
    ),
    LookPreset(
        name="slow_breathe_deep",
        movement_pattern="slow_breathe", speed_factor=0.25, amplitude_factor=1.3,
        dimmer_effect="static", chase_direction="none", chase_beats=16.0,
        chase_width=0.5, chase_intensity=0.0,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.15, color_saturation=0.3, color_contrast=0.15,
        moods=["ethereal", "chill", "ambient", "dark"],
        energy_min=0.0, energy_max=0.25,
        sections=["breakdown", "ethereal"],
        audio_characters=["sparse_ambient"],
        dominant_elements=["pad"],
        activity_range=(0.0, 0.2), density_range=(0.0, 0.25),
        ambiance_range=(0.6, 1.0), drive_range=(0.0, 0.15),
        texture_labels=["ambient"],
    ),
    LookPreset(
        name="audience_glow",
        movement_pattern="audience_scan", speed_factor=0.35, amplitude_factor=1.2,
        dimmer_effect="ramp", chase_direction="center_out", chase_beats=8.0,
        chase_width=0.35, chase_intensity=0.15,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.18, color_saturation=0.35, color_contrast=0.2,
        moods=["ethereal", "chill"],
        energy_min=0.0, energy_max=0.3,
        sections=["breakdown", "verse"],
        audio_characters=["sparse_ambient", "vocal_heavy"],
        dominant_elements=["pad", "vocal"],
        activity_range=(0.0, 0.35), density_range=(0.0, 0.35),
        ambiance_range=(0.4, 1.0), drive_range=(0.0, 0.25),
        texture_labels=["ambient", "tonal"],
    ),
    LookPreset(
        name="moonlight_drift",
        movement_pattern="tilt_wave", speed_factor=0.2, amplitude_factor=1.0,
        dimmer_effect="static", chase_direction="none", chase_beats=8.0,
        chase_width=0.3, chase_intensity=0.0,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.12, color_saturation=0.25, color_contrast=0.1,
        moods=["dark", "ethereal", "ambient"],
        energy_min=0.0, energy_max=0.2,
        sections=["breakdown", "ethereal"],
        audio_characters=["sparse_ambient", "filtered"],
        dominant_elements=["pad", "noise"],
        activity_range=(0.0, 0.2), density_range=(0.0, 0.2),
        ambiance_range=(0.7, 1.0), drive_range=(0.0, 0.1),
        texture_labels=["ambient"],
    ),
    LookPreset(
        name="filtered_slow_chase",
        movement_pattern="slow_breathe", speed_factor=0.3, amplitude_factor=1.1,
        dimmer_effect="circular", chase_direction="forward", chase_beats=8.0,
        chase_width=0.35, chase_intensity=0.18,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.18, color_saturation=0.3, color_contrast=0.15,
        moods=["ethereal", "chill", "dark"],
        energy_min=0.0, energy_max=0.3,
        sections=["breakdown"],
        audio_characters=["filtered", "sparse_ambient"],
        dominant_elements=["pad", "lead_synth"],
        activity_range=(0.1, 0.4), density_range=(0.1, 0.35),
        ambiance_range=(0.4, 0.9), drive_range=(0.0, 0.2),
        texture_labels=["ambient", "tonal"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  VERSE / MODERATE ENERGY
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="mirror_chase_verse",
        movement_pattern="mirror_sweep", speed_factor=0.75, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="forward", chase_beats=4.0,
        chase_width=0.22, chase_intensity=0.35,
        bump_strength=0.12, bump_style="travel", strobe_mode="none",
        base_dimmer=0.50, color_saturation=0.6, color_contrast=0.4,
        moods=["party", "euphoric", "driving"],
        energy_min=0.25, energy_max=0.6,
        sections=["verse"],
        audio_characters=["synth_lead", "percussive"],
    ),
    LookPreset(
        name="symmetric_fan_verse",
        movement_pattern="symmetric_fan", speed_factor=0.7, amplitude_factor=0.9,
        dimmer_effect="odd_even", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.25, chase_intensity=0.30,
        bump_strength=0.10, bump_style="travel", strobe_mode="none",
        base_dimmer=0.48, color_saturation=0.55, color_contrast=0.35,
        moods=["chill", "euphoric", "driving"],
        energy_min=0.2, energy_max=0.55,
        sections=["verse"],
        audio_characters=["synth_lead", "vocal_heavy"],
    ),
    LookPreset(
        name="cascade_verse",
        movement_pattern="cascade", speed_factor=0.8, amplitude_factor=1.0,
        dimmer_effect="circular", chase_direction="center_out", chase_beats=4.0,
        chase_width=0.20, chase_intensity=0.32,
        bump_strength=0.14, bump_style="travel", strobe_mode="none",
        base_dimmer=0.52, color_saturation=0.6, color_contrast=0.45,
        moods=["party", "euphoric", "driving"],
        energy_min=0.3, energy_max=0.65,
        sections=["verse"],
        audio_characters=["percussive", "synth_lead"],
    ),
    LookPreset(
        name="tilt_wave_moody",
        movement_pattern="tilt_wave", speed_factor=0.65, amplitude_factor=0.85,
        dimmer_effect="ramp", chase_direction="forward", chase_beats=4.0,
        chase_width=0.28, chase_intensity=0.28,
        bump_strength=0.08, bump_style="downbeat_only", strobe_mode="none",
        base_dimmer=0.45, color_saturation=0.5, color_contrast=0.3,
        moods=["dark", "chill", "ambient"],
        energy_min=0.2, energy_max=0.5,
        sections=["verse"],
        audio_characters=["vocal_heavy", "filtered"],
    ),
    LookPreset(
        name="stagger_subtle",
        movement_pattern="stagger_sweep", speed_factor=0.75, amplitude_factor=0.95,
        dimmer_effect="chase", chase_direction="forward", chase_beats=4.0,
        chase_width=0.22, chase_intensity=0.30,
        bump_strength=0.12, bump_style="travel", strobe_mode="none",
        base_dimmer=0.48, color_saturation=0.6, color_contrast=0.4,
        moods=["chill", "driving", "euphoric"],
        energy_min=0.2, energy_max=0.55,
        sections=["verse"],
        audio_characters=["percussive", "synth_lead"],
    ),
    LookPreset(
        name="verse_bump_groove",
        movement_pattern="audience_scan", speed_factor=0.7, amplitude_factor=1.1,
        dimmer_effect="odd_even", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.24, chase_intensity=0.25,
        bump_strength=0.18, bump_style="travel", strobe_mode="none",
        base_dimmer=0.50, color_saturation=0.55, color_contrast=0.35,
        moods=["party", "euphoric"],
        energy_min=0.25, energy_max=0.6,
        sections=["verse"],
        audio_characters=["percussive", "drum_breakdown"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  BUILDUP (rising energy, tension)
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="circle_buildup",
        movement_pattern="symmetric_circle", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="circular", chase_direction="forward", chase_beats=2.0,
        chase_width=0.18, chase_intensity=0.45,
        bump_strength=0.20, bump_style="travel", strobe_mode="none",
        base_dimmer=0.60, color_saturation=0.7, color_contrast=0.5,
        moods=["party", "aggressive", "driving"],
        energy_min=0.35, energy_max=0.8,
        sections=["buildup"],
        audio_characters=["noise_riser", "percussive"],
    ),
    LookPreset(
        name="cross_tilt_tension",
        movement_pattern="cross_tilt", speed_factor=1.1, amplitude_factor=1.05,
        dimmer_effect="chase", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.16, chase_intensity=0.48,
        bump_strength=0.22, bump_style="travel", strobe_mode="none",
        base_dimmer=0.58, color_saturation=0.75, color_contrast=0.55,
        moods=["aggressive", "driving"],
        energy_min=0.4, energy_max=0.85,
        sections=["buildup"],
        audio_characters=["noise_riser", "fast_transients"],
    ),
    LookPreset(
        name="buildup_strobe_accel",
        movement_pattern="stagger_sweep", speed_factor=1.05, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="forward", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.50,
        bump_strength=0.22, bump_style="travel",
        strobe_mode="buildup_accel",  # accelerating strobe
        base_dimmer=0.60, color_saturation=0.7, color_contrast=0.5,
        moods=["aggressive", "party"],
        energy_min=0.4, energy_max=0.85,
        sections=["buildup"],
        audio_characters=["noise_riser", "fast_transients"],
    ),
    LookPreset(
        name="mirror_accelerate",
        movement_pattern="mirror_sweep", speed_factor=1.0, amplitude_factor=1.1,
        dimmer_effect="ramp", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.50,
        bump_strength=0.18, bump_style="travel", strobe_mode="none",
        base_dimmer=0.55, color_saturation=0.65, color_contrast=0.45,
        moods=["party", "euphoric"],
        energy_min=0.35, energy_max=0.75,
        sections=["buildup"],
        audio_characters=["synth_lead", "noise_riser"],
    ),
    LookPreset(
        name="buildup_blinder_pulse",
        movement_pattern="symmetric_circle", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="odd_even", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.16, chase_intensity=0.45,
        bump_strength=0.25, bump_style="travel",
        strobe_mode="none", blinder_mode="pulse",
        base_dimmer=0.58, color_saturation=0.7, color_contrast=0.5,
        moods=["party", "aggressive"],
        energy_min=0.4, energy_max=0.85,
        sections=["buildup"],
        audio_characters=["percussive", "noise_riser"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  CHORUS (high energy, sustained)
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="ballyhoo_full",
        movement_pattern="ballyhoo", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.50,
        bump_strength=0.28, bump_style="travel", strobe_mode="none",
        base_dimmer=0.80, color_saturation=0.85, color_contrast=0.6,
        moods=["party", "euphoric"],
        energy_min=0.5, energy_max=1.0,
        sections=["chorus"],
        audio_characters=["synth_lead", "full_wall"],
    ),
    LookPreset(
        name="symmetric_circle_chorus",
        movement_pattern="symmetric_circle", speed_factor=1.0, amplitude_factor=1.1,
        dimmer_effect="circular", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.48,
        bump_strength=0.25, bump_style="travel", strobe_mode="none",
        base_dimmer=0.78, color_saturation=0.8, color_contrast=0.55,
        moods=["party", "euphoric", "driving"],
        energy_min=0.45, energy_max=1.0,
        sections=["chorus"],
        audio_characters=["synth_lead", "percussive", "full_wall"],
    ),
    LookPreset(
        name="figure8_wide_chorus",
        movement_pattern="figure_eight_wide", speed_factor=0.95, amplitude_factor=1.15,
        dimmer_effect="ramp", chase_direction="forward", chase_beats=2.0,
        chase_width=0.16, chase_intensity=0.45,
        bump_strength=0.22, bump_style="travel", strobe_mode="none",
        base_dimmer=0.82, color_saturation=0.8, color_contrast=0.5,
        moods=["euphoric", "chill"],
        energy_min=0.4, energy_max=0.9,
        sections=["chorus"],
        audio_characters=["synth_lead", "vocal_heavy"],
    ),
    LookPreset(
        name="chorus_strobe_hits",
        movement_pattern="cascade", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.50,
        bump_strength=0.25, bump_style="travel",
        strobe_mode="beat_pulse",  # strobe on beats
        base_dimmer=0.80, color_saturation=0.85, color_contrast=0.6,
        moods=["party", "aggressive"],
        energy_min=0.5, energy_max=1.0,
        sections=["chorus"],
        audio_characters=["fast_transients", "full_wall"],
    ),
    LookPreset(
        name="snap_look_chorus",
        movement_pattern="snap_look", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="odd_even", chase_direction="bounce", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55,
        bump_strength=0.30, bump_style="all", strobe_mode="none",
        base_dimmer=0.82, color_saturation=0.85, color_contrast=0.6,
        moods=["aggressive", "party"],
        energy_min=0.55, energy_max=1.0,
        sections=["chorus"],
        audio_characters=["percussive", "fast_transients"],
    ),
    LookPreset(
        name="chorus_fast_chase",
        movement_pattern="mirror_sweep", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55,
        bump_strength=0.30, bump_style="travel", strobe_mode="none",
        base_dimmer=0.85, color_saturation=0.9, color_contrast=0.65,
        moods=["aggressive", "driving"],
        energy_min=0.55, energy_max=1.0,
        sections=["chorus"],
        audio_characters=["fast_transients", "percussive", "full_wall"],
    ),
    LookPreset(
        name="stagger_chorus",
        movement_pattern="stagger_sweep", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="ramp", chase_direction="forward", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.50,
        bump_strength=0.25, bump_style="travel", strobe_mode="none",
        base_dimmer=0.80, color_saturation=0.8, color_contrast=0.55,
        moods=["party", "euphoric", "driving"],
        energy_min=0.45, energy_max=1.0,
        sections=["chorus"],
        audio_characters=["synth_lead", "percussive"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  DROP (maximum energy) — varied responses, NOT always strobes
    # ════════════════════════════════════════════════════════════════

    # Drop look: STROBE on eighth notes (classic EDM drop)
    LookPreset(
        name="drop_strobe_eighth",
        movement_pattern="center_burst", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55,
        bump_strength=0.40, bump_style="all",
        strobe_mode="eighth_note",
        base_dimmer=0.95, color_saturation=1.0, color_contrast=0.7,
        moods=["aggressive", "party"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
        audio_characters=["heavy_bass", "fast_transients", "impact", "full_wall"],
    ),
    # Drop look: FAST SYNTH strobe (for synth-heavy drops)
    LookPreset(
        name="drop_synth_strobe",
        movement_pattern="sync_sweep", speed_factor=1.3, amplitude_factor=1.0,
        dimmer_effect="odd_even", chase_direction="bounce", chase_beats=0.5,
        chase_width=0.10, chase_intensity=0.60,
        bump_strength=0.35, bump_style="travel",
        strobe_mode="fast_synth",
        base_dimmer=0.90, color_saturation=1.0, color_contrast=0.7,
        moods=["aggressive", "driving"],
        energy_min=0.65, energy_max=1.0,
        sections=["drop"],
        audio_characters=["fast_transients", "synth_lead"],
    ),
    # Drop look: NO strobe, fast traveling chase instead
    LookPreset(
        name="drop_fast_chase",
        movement_pattern="ballyhoo", speed_factor=1.25, amplitude_factor=1.1,
        dimmer_effect="chase", chase_direction="forward", chase_beats=0.5,
        chase_width=0.10, chase_intensity=0.60,
        bump_strength=0.38, bump_style="travel",
        strobe_mode="none",
        base_dimmer=0.95, color_saturation=0.95, color_contrast=0.65,
        moods=["party", "euphoric"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
        audio_characters=["heavy_bass", "full_wall"],
    ),
    # Drop look: NO strobe, heavy bumps traveling through rig
    LookPreset(
        name="drop_bump_wave",
        movement_pattern="stagger_sweep", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="circular", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.55,
        bump_strength=0.50, bump_style="travel",
        strobe_mode="none",
        base_dimmer=0.90, color_saturation=1.0, color_contrast=0.7,
        moods=["aggressive", "driving"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
        audio_characters=["heavy_bass", "percussive", "impact"],
    ),
    # Drop look: random strobe bursts (unpredictable, exciting)
    LookPreset(
        name="drop_random_burst",
        movement_pattern="center_burst", speed_factor=1.15, amplitude_factor=1.0,
        dimmer_effect="ramp", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55,
        bump_strength=0.42, bump_style="all",
        strobe_mode="random_burst",
        base_dimmer=0.95, color_saturation=1.0, color_contrast=0.7,
        moods=["aggressive", "party"],
        energy_min=0.7, energy_max=1.0,
        sections=["drop"],
        audio_characters=["fast_transients", "impact", "full_wall"],
    ),
    # Drop look: massive sweeping movement, kick-locked strobe
    LookPreset(
        name="drop_sweep_power",
        movement_pattern="sync_sweep", speed_factor=1.3, amplitude_factor=1.2,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.55,
        bump_strength=0.35, bump_style="travel",
        strobe_mode="kick_locked",
        base_dimmer=0.92, color_saturation=1.0, color_contrast=0.6,
        moods=["euphoric", "driving"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
        audio_characters=["synth_lead", "full_wall", "four_on_floor"],
    ),
    # Drop look: snap looks on beats, drum hit strobes
    LookPreset(
        name="drop_snap_burst",
        movement_pattern="snap_look", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="odd_even", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.58,
        bump_strength=0.42, bump_style="all",
        strobe_mode="drum_hits",
        base_dimmer=0.95, color_saturation=1.0, color_contrast=0.7,
        moods=["aggressive", "party"],
        energy_min=0.7, energy_max=1.0,
        sections=["drop"],
        audio_characters=["percussive", "fast_transients", "impact", "drum_heavy"],
    ),
    # Drop look: kick-locked strobe + kick/clap dimmer — maximum drum sync
    LookPreset(
        name="drop_kick_locked_full",
        movement_pattern="center_burst", speed_factor=1.15, amplitude_factor=1.0,
        dimmer_effect="kick_clap", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.70,
        bump_strength=0.45, bump_style="all",
        strobe_mode="kick_locked",
        base_dimmer=0.90, color_saturation=1.0, color_contrast=0.75,
        moods=["aggressive", "driving"],
        energy_min=0.60, energy_max=1.0,
        sections=["drop"],
        audio_characters=["four_on_floor", "heavy_bass", "drum_heavy", "pounding"],
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.6, 1.0),
        density_range=(0.5, 1.0),
    ),
    # Drop look: snare-flash strobe + fast chase — for snare-heavy drops
    LookPreset(
        name="drop_snare_flash",
        movement_pattern="ballyhoo", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="forward", chase_beats=0.5,
        chase_width=0.10, chase_intensity=0.60,
        bump_strength=0.38, bump_style="travel",
        strobe_mode="snare_locked",
        base_dimmer=0.88, color_saturation=0.95, color_contrast=0.65,
        moods=["aggressive", "party"],
        energy_min=0.55, energy_max=1.0,
        sections=["drop", "chorus"],
        audio_characters=["percussive", "drum_heavy"],
    ),
    # Drop look: blinder slam on every beat
    LookPreset(
        name="drop_blinder_slam",
        movement_pattern="ballyhoo", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="forward", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55,
        bump_strength=0.40, bump_style="travel",
        strobe_mode="none", blinder_mode="beat_slam",
        base_dimmer=0.95, color_saturation=1.0, color_contrast=0.65,
        moods=["party", "aggressive"],
        energy_min=0.6, energy_max=1.0,
        sections=["drop"],
        audio_characters=["heavy_bass", "impact", "full_wall"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  DRUM BREAKDOWN — stripped drums, rhythmic focus
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="drum_break_bumps",
        movement_pattern="snap_look", speed_factor=0.9, amplitude_factor=0.8,
        dimmer_effect="odd_even", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.18, chase_intensity=0.40,
        bump_strength=0.45, bump_style="travel",  # heavy traveling bumps on drums
        strobe_mode="none",
        base_dimmer=0.55, color_saturation=0.6, color_contrast=0.5,
        moods=["driving", "aggressive", "party"],
        energy_min=0.3, energy_max=0.7,
        sections=["verse", "buildup", "chorus"],
        audio_characters=["drum_breakdown", "percussive"],
        weight=1.5,  # boosted weight for drum sections
    ),
    LookPreset(
        name="drum_break_fast_chase",
        movement_pattern="stagger_sweep", speed_factor=1.1, amplitude_factor=0.9,
        dimmer_effect="chase", chase_direction="forward", chase_beats=1.0,
        chase_width=0.14, chase_intensity=0.50,
        bump_strength=0.35, bump_style="travel",
        strobe_mode="none",
        base_dimmer=0.60, color_saturation=0.65, color_contrast=0.5,
        moods=["driving", "aggressive"],
        energy_min=0.3, energy_max=0.7,
        sections=["verse", "buildup"],
        audio_characters=["drum_breakdown", "percussive"],
        weight=1.5,
    ),
    LookPreset(
        name="drum_break_strobe_burst",
        movement_pattern="mirror_sweep", speed_factor=0.9, amplitude_factor=0.85,
        dimmer_effect="circular", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.16, chase_intensity=0.42,
        bump_strength=0.40, bump_style="travel",
        strobe_mode="random_burst",  # occasional strobe bursts on drum hits
        base_dimmer=0.50, color_saturation=0.6, color_contrast=0.5,
        moods=["aggressive", "driving"],
        energy_min=0.35, energy_max=0.75,
        sections=["verse", "buildup", "chorus"],
        audio_characters=["drum_breakdown", "fast_transients"],
        weight=1.2,
    ),

    # ════════════════════════════════════════════════════════════════
    #  FAST TRANSIENT / SYNTH STAB LOOKS
    #  (rapid synth arps, stabs — sometimes strobe, sometimes fast chase)
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="synth_stab_strobe",
        movement_pattern="symmetric_fan", speed_factor=1.1, amplitude_factor=0.9,
        dimmer_effect="odd_even", chase_direction="bounce", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.50,
        bump_strength=0.30, bump_style="travel",
        strobe_mode="fast_synth",  # short strobe bursts matching transients
        base_dimmer=0.70, color_saturation=0.8, color_contrast=0.6,
        moods=["aggressive", "driving", "party"],
        energy_min=0.45, energy_max=1.0,
        sections=["chorus", "drop", "buildup"],
        audio_characters=["fast_transients", "synth_lead"],
        weight=1.3,
    ),
    LookPreset(
        name="synth_stab_fast_chase",
        movement_pattern="cascade", speed_factor=1.3, amplitude_factor=1.0,
        dimmer_effect="chase", chase_direction="forward", chase_beats=0.5,
        chase_width=0.10, chase_intensity=0.58,
        bump_strength=0.25, bump_style="travel",
        strobe_mode="none",  # fast chase instead of strobe
        base_dimmer=0.75, color_saturation=0.85, color_contrast=0.6,
        moods=["party", "euphoric", "driving"],
        energy_min=0.45, energy_max=1.0,
        sections=["chorus", "drop", "buildup"],
        audio_characters=["fast_transients", "synth_lead"],
        weight=1.3,
    ),
    LookPreset(
        name="synth_stab_rapid_movement",
        movement_pattern="cross_tilt", speed_factor=1.5, amplitude_factor=0.9,
        dimmer_effect="ramp", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.50,
        bump_strength=0.28, bump_style="travel",
        strobe_mode="none",  # fast movement instead of strobe
        base_dimmer=0.72, color_saturation=0.8, color_contrast=0.55,
        moods=["aggressive", "driving"],
        energy_min=0.5, energy_max=1.0,
        sections=["chorus", "drop"],
        audio_characters=["fast_transients"],
        weight=1.2,
    ),

    # ════════════════════════════════════════════════════════════════
    #  HEAVY BASS — sub-heavy sections
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="bass_heavy_bump",
        movement_pattern="ballyhoo", speed_factor=1.0, amplitude_factor=1.1,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=1.0,
        chase_width=0.14, chase_intensity=0.50,
        bump_strength=0.50, bump_style="travel",  # massive bumps on bass
        strobe_mode="none",
        base_dimmer=0.85, color_saturation=0.9, color_contrast=0.6,
        moods=["aggressive", "driving", "dark"],
        energy_min=0.5, energy_max=1.0,
        sections=["drop", "chorus"],
        audio_characters=["heavy_bass"],
        weight=1.3,
    ),
    LookPreset(
        name="bass_heavy_odd_even",
        movement_pattern="stagger_sweep", speed_factor=1.0, amplitude_factor=1.0,
        dimmer_effect="odd_even", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.52,
        bump_strength=0.45, bump_style="all",
        strobe_mode="none",
        base_dimmer=0.88, color_saturation=0.95, color_contrast=0.65,
        moods=["aggressive", "dark"],
        energy_min=0.55, energy_max=1.0,
        sections=["drop", "chorus"],
        audio_characters=["heavy_bass", "percussive"],
        weight=1.2,
    ),

    # ════════════════════════════════════════════════════════════════
    #  VOCAL HEAVY — prominent vocals
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="vocal_spotlight",
        movement_pattern="audience_scan", speed_factor=0.7, amplitude_factor=1.0,
        dimmer_effect="ramp", chase_direction="center_out", chase_beats=4.0,
        chase_width=0.25, chase_intensity=0.30,
        bump_strength=0.10, bump_style="downbeat_only", strobe_mode="none",
        base_dimmer=0.55, color_saturation=0.6, color_contrast=0.4,
        moods=["chill", "euphoric", "ambient"],
        energy_min=0.2, energy_max=0.6,
        sections=["verse", "chorus"],
        audio_characters=["vocal_heavy"],
    ),
    LookPreset(
        name="vocal_sweep",
        movement_pattern="tilt_wave", speed_factor=0.65, amplitude_factor=1.1,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.22, chase_intensity=0.28,
        bump_strength=0.08, bump_style="downbeat_only", strobe_mode="none",
        base_dimmer=0.52, color_saturation=0.55, color_contrast=0.35,
        moods=["chill", "dark", "euphoric"],
        energy_min=0.2, energy_max=0.55,
        sections=["verse", "breakdown"],
        audio_characters=["vocal_heavy", "sparse_ambient"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  IMPACT / TRANSITION MOMENTS
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="impact_blackout_flash",
        movement_pattern="center_burst", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="static", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.55,
        bump_strength=0.60, bump_style="all",  # massive all-fixture bump
        strobe_mode="beat_pulse",
        base_dimmer=0.10, blinder_mode="beat_slam",
        color_saturation=1.0, color_contrast=0.8,
        moods=["aggressive", "party"],
        energy_min=0.7, energy_max=1.0,
        sections=["drop"],
        audio_characters=["impact"],
        weight=2.0,  # high weight — impacts should feel special
    ),

    # ════════════════════════════════════════════════════════════════
    #  FILTERED / SWEEP SECTIONS
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="filtered_fade",
        movement_pattern="slow_breathe", speed_factor=0.4, amplitude_factor=1.0,
        dimmer_effect="ramp", chase_direction="forward", chase_beats=8.0,
        chase_width=0.30, chase_intensity=0.20,
        bump_strength=0.05, bump_style="downbeat_only", strobe_mode="none",
        base_dimmer=0.30, color_saturation=0.4, color_contrast=0.2,
        moods=["chill", "dark", "ambient"],
        energy_min=0.1, energy_max=0.45,
        sections=["verse", "breakdown"],
        audio_characters=["filtered"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  PRE-DROP PREPARATION looks (selected when drop is predicted)
    #  These dim down and tighten up to create maximum contrast
    # ════════════════════════════════════════════════════════════════

    LookPreset(
        name="predrop_tighten_dark",
        movement_pattern="slow_breathe", speed_factor=0.4, amplitude_factor=0.6,
        dimmer_effect="static", chase_direction="none", chase_beats=8.0,
        chase_width=0.3, chase_intensity=0.0,
        bump_strength=0.05, bump_style="downbeat_only", strobe_mode="none",
        base_dimmer=0.15, color_saturation=0.3, color_contrast=0.15,
        moods=["aggressive", "driving", "party", "euphoric"],
        energy_min=0.2, energy_max=0.8,
        sections=["predrop"],  # special section tag
        audio_characters=["noise_riser", "sparse_ambient"],
    ),
    LookPreset(
        name="predrop_narrow_focus",
        movement_pattern="tilt_wave", speed_factor=0.35, amplitude_factor=0.5,
        dimmer_effect="ramp", chase_direction="center_out", chase_beats=8.0,
        chase_width=0.25, chase_intensity=0.12,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.12, color_saturation=0.25, color_contrast=0.1,
        moods=["aggressive", "driving", "dark"],
        energy_min=0.1, energy_max=0.7,
        sections=["predrop"],
        audio_characters=["noise_riser", "filtered"],
    ),
    LookPreset(
        name="predrop_freeze",
        movement_pattern="fly_out", speed_factor=0.2, amplitude_factor=0.4,
        dimmer_effect="static", chase_direction="none", chase_beats=16.0,
        chase_width=0.4, chase_intensity=0.0,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.08, color_saturation=0.2, color_contrast=0.1,
        moods=["ethereal", "aggressive", "dark"],
        energy_min=0.0, energy_max=0.6,
        sections=["predrop"],
        audio_characters=["noise_riser", "sparse_ambient"],
    ),

    # ════════════════════════════════════════════════════════════════
    #  ISOLATED / DARK MOMENT LOOKS (fixture group isolation)
    # ════════════════════════════════════════════════════════════════
    # These looks only light specific fixture groups, keeping everything
    # else in near-blackout. Creates dramatic contrast and focus.

    # Beams only — sharp aerial beams cutting through darkness
    LookPreset(
        name="beams_only_sweep",
        movement_pattern="mirror_sweep", speed_factor=0.9, amplitude_factor=0.90,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.80,
        bump_strength=0.25, bump_style="travel", strobe_mode="none",
        base_dimmer=0.85, color_saturation=0.90, color_contrast=0.55,
        moods=["driving", "party", "aggressive"],
        energy_min=0.30, energy_max=0.85,
        sections=["verse", "chorus"],
        audio_characters=["percussive", "synth_lead"],
        active_groups=["beam"], isolation_floor=0.02,
        drive_range=(0.3, 0.8),
    ),
    LookPreset(
        name="beams_only_fan",
        movement_pattern="symmetric_fan", speed_factor=0.8, amplitude_factor=0.85,
        dimmer_effect="kick_clap", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.14, chase_intensity=0.75,
        bump_strength=0.30, bump_style="all", strobe_mode="none",
        base_dimmer=0.90, color_saturation=0.85, color_contrast=0.60,
        moods=["driving", "aggressive"],
        energy_min=0.35, energy_max=0.95,
        sections=["drop", "chorus"],
        audio_characters=["four_on_floor", "drum_heavy", "heavy_bass"],
        active_groups=["beam"], isolation_floor=0.02,
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.4, 1.0),
    ),
    # Beams-only ballyhoo during drops — the classic "big show" moment
    LookPreset(
        name="beams_only_drop",
        movement_pattern="ballyhoo", speed_factor=1.15, amplitude_factor=1.0,
        dimmer_effect="left_right_kick", chase_direction="forward", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.85,
        bump_strength=0.40, bump_style="all", strobe_mode="kick_locked",
        base_dimmer=0.95, color_saturation=1.0, color_contrast=0.70,
        moods=["aggressive", "driving"],
        energy_min=0.50, energy_max=1.0,
        sections=["drop"],
        audio_characters=["four_on_floor", "heavy_bass", "pounding", "drum_heavy"],
        active_groups=["beam"], isolation_floor=0.0,
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.5, 1.0),
    ),

    # Washes only — soft fill with everything else dark
    LookPreset(
        name="washes_only_breathe",
        movement_pattern="slow_breathe", speed_factor=0.4, amplitude_factor=0.50,
        dimmer_effect="ramp", chase_direction="forward", chase_beats=8.0,
        chase_width=0.30, chase_intensity=0.55,
        bump_strength=0.0, bump_style="none", strobe_mode="none",
        base_dimmer=0.50, color_saturation=0.45, color_contrast=0.30,
        moods=["ethereal", "chill"],
        energy_min=0.0, energy_max=0.35,
        sections=["breakdown"],
        audio_characters=["sparse_ambient", "no_drums"],
        active_groups=["wash"], isolation_floor=0.01,
        ambiance_range=(0.4, 1.0),
        drive_range=(0.0, 0.2),
    ),

    # Bars + washes only — floor glow with wash fills, beams dark
    LookPreset(
        name="floor_wash_verse",
        movement_pattern="audience_scan", speed_factor=0.6, amplitude_factor=0.55,
        dimmer_effect="chase", chase_direction="forward", chase_beats=4.0,
        chase_width=0.20, chase_intensity=0.60,
        bump_strength=0.10, bump_style="travel", strobe_mode="none",
        base_dimmer=0.55, color_saturation=0.55, color_contrast=0.40,
        moods=["chill", "driving"],
        energy_min=0.15, energy_max=0.50,
        sections=["verse"],
        audio_characters=["synth_lead"],
        active_groups=["bar", "wash"], isolation_floor=0.02,
        drive_range=(0.2, 0.5),
    ),

    # Beams + strobes only — maximum impact drop moment
    LookPreset(
        name="beams_strobes_drop",
        movement_pattern="center_burst", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="kick_clap", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.85,
        bump_strength=0.45, bump_style="all", strobe_mode="drum_hits",
        base_dimmer=1.0, color_saturation=1.0, color_contrast=0.75,
        moods=["aggressive"],
        energy_min=0.60, energy_max=1.0,
        sections=["drop"],
        audio_characters=["four_on_floor", "heavy_bass", "pounding", "impact", "drum_heavy"],
        active_groups=["beam", "strobe"], isolation_floor=0.0,
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.7, 1.0),
        density_range=(0.6, 1.0),
    ),

    # ════════════════════════════════════════════════════════════════
    #  CHASE-HEAVY LOOKS (visible traveling dimmers)
    # ════════════════════════════════════════════════════════════════
    # These looks prioritize visible dimmer chases running through the rig.
    # The chase_intensity is high so there's real contrast between
    # "on" and "off" fixtures — not just a subtle bump.

    # Strong forward chase across all fixtures — verse/chorus staple
    LookPreset(
        name="chase_forward_verse",
        movement_pattern="audience_scan", speed_factor=0.7, amplitude_factor=0.65,
        dimmer_effect="chase", chase_direction="forward", chase_beats=4.0,
        chase_width=0.18, chase_intensity=0.70,
        bump_strength=0.15, bump_style="travel", strobe_mode="none",
        base_dimmer=0.55, color_saturation=0.60, color_contrast=0.45,
        moods=["chill", "driving", "party"],
        energy_min=0.20, energy_max=0.65,
        sections=["verse"],
        audio_characters=["percussive", "synth_lead"],
        drive_range=(0.2, 0.6),
    ),
    # Bouncing chase — travels left→right→left with color
    LookPreset(
        name="chase_bounce_chorus",
        movement_pattern="mirror_sweep", speed_factor=1.0, amplitude_factor=0.85,
        dimmer_effect="chase", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.75,
        bump_strength=0.25, bump_style="travel", strobe_mode="none",
        base_dimmer=0.70, color_saturation=0.80, color_contrast=0.55,
        moods=["party", "euphoric", "driving"],
        energy_min=0.40, energy_max=0.90,
        sections=["chorus"],
        audio_characters=["percussive", "full_wall", "synth_lead"],
        drive_range=(0.4, 0.9),
    ),
    # Center-out chase — expanding from center during drops
    LookPreset(
        name="chase_center_out_drop",
        movement_pattern="symmetric_fan", speed_factor=1.1, amplitude_factor=0.95,
        dimmer_effect="chase", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.80,
        bump_strength=0.35, bump_style="all", strobe_mode="none",
        base_dimmer=0.85, color_saturation=0.95, color_contrast=0.65,
        moods=["driving", "aggressive", "party"],
        energy_min=0.50, energy_max=1.0,
        sections=["drop", "chorus"],
        audio_characters=["heavy_bass", "full_wall"],
        drive_range=(0.5, 1.0),
    ),
    # Ramp wave across rig — smooth intensity sweep
    LookPreset(
        name="ramp_wave_verse",
        movement_pattern="tilt_wave", speed_factor=0.65, amplitude_factor=0.60,
        dimmer_effect="ramp", chase_direction="forward", chase_beats=4.0,
        chase_width=0.20, chase_intensity=0.65,
        bump_strength=0.12, bump_style="travel", strobe_mode="none",
        base_dimmer=0.50, color_saturation=0.55, color_contrast=0.40,
        moods=["chill", "driving"],
        energy_min=0.15, energy_max=0.55,
        sections=["verse"],
        audio_characters=["synth_lead"],
        drive_range=(0.2, 0.5),
    ),
    # Fast circular chase during high energy
    LookPreset(
        name="chase_circular_fast",
        movement_pattern="ballyhoo", speed_factor=1.2, amplitude_factor=1.0,
        dimmer_effect="circular", chase_direction="forward", chase_beats=1.0,
        chase_width=0.10, chase_intensity=0.75,
        bump_strength=0.30, bump_style="travel", strobe_mode="none",
        base_dimmer=0.80, color_saturation=0.90, color_contrast=0.60,
        moods=["party", "driving", "aggressive"],
        energy_min=0.50, energy_max=1.0,
        sections=["chorus", "drop"],
        audio_characters=["fast_transients", "percussive", "full_wall"],
        drive_range=(0.5, 1.0),
    ),

    # ════════════════════════════════════════════════════════════════
    #  DRUM-DRIVEN LOOKS (powered by DrumIntelligence)
    # ════════════════════════════════════════════════════════════════
    # These looks use actual kick/snare hits for dimmer effects,
    # making the rig respond to the real groove, not just BPM phase.
    # Tagged for sections/moods where drums dominate the feel.

    # ── Kick/Clap alternating: odd fixtures fire on kick, even on snare ──
    # Classic EDM lighting — the rig breathes with the groove.
    # Works best with four-on-floor + strong snare on 2&4.
    LookPreset(
        name="kick_clap_mirror_sweep",
        movement_pattern="mirror_sweep", speed_factor=0.9, amplitude_factor=0.85,
        dimmer_effect="kick_clap", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.18, chase_intensity=0.65,
        bump_strength=0.35, bump_style="all", strobe_mode="none",
        base_dimmer=0.40, color_saturation=0.75, color_contrast=0.6,
        moods=["driving", "party", "aggressive"],
        energy_min=0.35, energy_max=1.0,
        sections=["drop", "chorus"],
        audio_characters=["four_on_floor", "heavy_bass", "drum_heavy", "percussive"],
        # High drive, drums/bass dominant, dense, dry — peak energy sections
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.5, 1.0),
        density_range=(0.4, 1.0),
        ambiance_range=(0.0, 0.4),
        texture_labels=["percussive", "driving"],
    ),
    LookPreset(
        name="kick_clap_symmetric_fan",
        movement_pattern="symmetric_fan", speed_factor=0.8, amplitude_factor=0.9,
        dimmer_effect="kick_clap", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.15, chase_intensity=0.60,
        bump_strength=0.30, bump_style="travel", strobe_mode="none",
        base_dimmer=0.35, color_saturation=0.70, color_contrast=0.55,
        moods=["driving", "party", "euphoric"],
        energy_min=0.30, energy_max=0.90,
        sections=["chorus", "drop", "verse"],
        audio_characters=["four_on_floor", "drum_heavy", "percussive"],
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.4, 1.0),
        density_range=(0.3, 0.9),
        texture_labels=["percussive", "driving"],
    ),

    # ── Kick/Clap with center burst: explosive on kick, snap on clap ──
    # High intensity version — for peak drop moments
    LookPreset(
        name="kick_clap_center_burst",
        movement_pattern="center_burst", speed_factor=1.1, amplitude_factor=1.0,
        dimmer_effect="kick_clap", chase_direction="center_out", chase_beats=1.0,
        chase_width=0.12, chase_intensity=0.75,
        bump_strength=0.45, bump_style="all", strobe_mode="beat_pulse",
        base_dimmer=0.45, color_saturation=0.80, color_contrast=0.70,
        moods=["aggressive", "driving"],
        energy_min=0.45, energy_max=1.0,
        sections=["drop"],
        audio_characters=["four_on_floor", "heavy_bass", "drum_heavy", "pounding", "impact"],
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.6, 1.0),
        density_range=(0.5, 1.0),
        ambiance_range=(0.0, 0.3),
        texture_labels=["percussive"],
    ),

    # ── Left/Right kick: left side fires on kick, right on snare ──
    # Dramatic side-to-side pumping across the entire rig
    LookPreset(
        name="left_right_kick_sweep",
        movement_pattern="sync_sweep", speed_factor=0.85, amplitude_factor=0.80,
        dimmer_effect="left_right_kick", chase_direction="bounce", chase_beats=2.0,
        chase_width=0.20, chase_intensity=0.60,
        bump_strength=0.30, bump_style="all", strobe_mode="none",
        base_dimmer=0.38, color_saturation=0.72, color_contrast=0.55,
        moods=["driving", "party", "aggressive"],
        energy_min=0.30, energy_max=1.0,
        sections=["drop", "chorus"],
        audio_characters=["four_on_floor", "drum_heavy", "percussive"],
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.5, 1.0),
        density_range=(0.4, 1.0),
        texture_labels=["percussive", "driving"],
    ),
    LookPreset(
        name="left_right_kick_ballyhoo",
        movement_pattern="ballyhoo", speed_factor=1.0, amplitude_factor=0.90,
        dimmer_effect="left_right_kick", chase_direction="forward", chase_beats=1.0,
        chase_width=0.14, chase_intensity=0.70,
        bump_strength=0.40, bump_style="travel", strobe_mode="none",
        base_dimmer=0.42, color_saturation=0.78, color_contrast=0.65,
        moods=["aggressive", "driving", "party"],
        energy_min=0.40, energy_max=1.0,
        sections=["drop"],
        audio_characters=["four_on_floor", "heavy_bass", "pounding", "drum_heavy"],
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.6, 1.0),
        density_range=(0.5, 1.0),
        ambiance_range=(0.0, 0.3),
        texture_labels=["percussive"],
    ),

    # ── Kick/Clap with half-time groove: slower pulse, heavier ──
    # For half-time drops (dubstep-style, trap-influenced EDM)
    LookPreset(
        name="kick_clap_halftime",
        movement_pattern="cross_tilt", speed_factor=0.6, amplitude_factor=0.75,
        dimmer_effect="kick_clap", chase_direction="bounce", chase_beats=4.0,
        chase_width=0.22, chase_intensity=0.55,
        bump_strength=0.40, bump_style="downbeat_only", strobe_mode="none",
        base_dimmer=0.35, color_saturation=0.65, color_contrast=0.50,
        moods=["aggressive", "dark", "driving"],
        energy_min=0.25, energy_max=0.85,
        sections=["drop", "chorus", "verse"],
        audio_characters=["half_time", "heavy_bass", "percussive"],
        dominant_elements=["drums", "bass_synth"],
        drive_range=(0.3, 0.8),
        density_range=(0.3, 0.8),
        texture_labels=["percussive"],
    ),

    # ── Drum-driven verse: subtle kick/clap pulse during regular verse ──
    # Gentle version for when drums carry a verse without being overwhelming
    LookPreset(
        name="drum_verse_pulse",
        movement_pattern="audience_scan", speed_factor=0.7, amplitude_factor=0.65,
        dimmer_effect="kick_clap", chase_direction="forward", chase_beats=4.0,
        chase_width=0.25, chase_intensity=0.35,
        bump_strength=0.18, bump_style="all", strobe_mode="none",
        base_dimmer=0.45, color_saturation=0.55, color_contrast=0.35,
        moods=["chill", "driving", "party"],
        energy_min=0.15, energy_max=0.60,
        sections=["verse"],
        audio_characters=["four_on_floor", "percussive", "drum_heavy"],
        dominant_elements=["drums"],
        drive_range=(0.25, 0.6),
        density_range=(0.2, 0.6),
        texture_labels=["percussive", "driving"],
    ),

    # ── Snare-roll buildup: left/right alternation accelerates with snare ──
    # For buildup sections where snare roll drives the tension
    LookPreset(
        name="snare_roll_buildup",
        movement_pattern="tilt_wave", speed_factor=0.7, amplitude_factor=0.60,
        dimmer_effect="left_right_kick", chase_direction="center_out", chase_beats=2.0,
        chase_width=0.18, chase_intensity=0.50,
        bump_strength=0.25, bump_style="travel", strobe_mode="buildup_accel",
        base_dimmer=0.30, color_saturation=0.60, color_contrast=0.45,
        moods=["party", "driving", "aggressive"],
        energy_min=0.20, energy_max=0.80,
        sections=["buildup"],
        audio_characters=["snare_roll", "noise_riser", "percussive"],
        dominant_elements=["drums", "noise"],
        drive_range=(0.2, 0.7),
        activity_range=(0.5, 1.0),
        texture_labels=["percussive"],
    ),
]


# ══════════════════════════════════════════════════════════════════════
#  AUTO-TAG LOOKS WITH MUSICAL FINGERPRINT RANGES
# ══════════════════════════════════════════════════════════════════════
# For looks that don't have explicit fingerprint ranges, derive them
# from their existing section/mood/audio_character/energy tags.
# This ensures backward compatibility while enabling distance matching.

_SECTION_FINGERPRINT_DEFAULTS = {
    "breakdown": {
        "dominant_elements": ["pad", "noise"],
        "activity_range": (0.0, 0.3),
        "density_range": (0.0, 0.3),
        "ambiance_range": (0.5, 1.0),
        "drive_range": (0.0, 0.2),
        "texture_labels": ["ambient"],
    },
    "ethereal": {
        "dominant_elements": ["pad"],
        "activity_range": (0.0, 0.2),
        "density_range": (0.0, 0.25),
        "ambiance_range": (0.6, 1.0),
        "drive_range": (0.0, 0.15),
        "texture_labels": ["ambient"],
    },
    "verse": {
        "dominant_elements": ["lead_synth", "vocal", "drums"],
        "activity_range": (0.2, 0.6),
        "density_range": (0.25, 0.6),
        "ambiance_range": (0.2, 0.6),
        "drive_range": (0.2, 0.6),
        "texture_labels": ["tonal", "driving"],
    },
    "buildup": {
        "dominant_elements": ["noise", "lead_synth", "drums"],
        "activity_range": (0.4, 0.9),
        "density_range": (0.3, 0.8),
        "ambiance_range": (0.2, 0.6),
        "drive_range": (0.3, 0.8),
        "texture_labels": ["driving", "noisy"],
    },
    "chorus": {
        "dominant_elements": ["lead_synth", "bass_synth", "drums"],
        "activity_range": (0.4, 0.8),
        "density_range": (0.5, 0.9),
        "ambiance_range": (0.1, 0.5),
        "drive_range": (0.5, 0.9),
        "texture_labels": ["driving", "tonal"],
    },
    "drop": {
        "dominant_elements": ["bass_synth", "drums"],
        "activity_range": (0.5, 1.0),
        "density_range": (0.6, 1.0),
        "ambiance_range": (0.0, 0.3),
        "drive_range": (0.6, 1.0),
        "texture_labels": ["percussive", "driving"],
    },
    "predrop": {
        "dominant_elements": ["noise", "pad"],
        "activity_range": (0.1, 0.4),
        "density_range": (0.1, 0.4),
        "ambiance_range": (0.3, 0.8),
        "drive_range": (0.1, 0.4),
        "texture_labels": ["noisy", "ambient"],
    },
}

# Audio character → fingerprint tweaks
_AUDIO_CHAR_TWEAKS = {
    "heavy_bass": {"dominant_elements": ["bass_synth"], "drive_range": (0.5, 1.0)},
    "synth_lead": {"dominant_elements": ["lead_synth"], "texture_labels": ["tonal"]},
    "drum_breakdown": {"dominant_elements": ["drums"], "density_range": (0.2, 0.5)},
    "sparse_ambient": {"dominant_elements": ["pad"], "ambiance_range": (0.5, 1.0)},
    "vocal_heavy": {"dominant_elements": ["vocal"]},
    "noise_riser": {"dominant_elements": ["noise"], "texture_labels": ["noisy"]},
    "fast_transients": {"activity_range": (0.6, 1.0), "texture_labels": ["percussive"]},
    "impact": {"activity_range": (0.7, 1.0), "density_range": (0.7, 1.0)},
    "full_wall": {"density_range": (0.7, 1.0), "drive_range": (0.6, 1.0)},
}


def _auto_tag_looks():
    """Apply default fingerprint ranges to looks that don't have them."""
    for look in LOOK_LIBRARY:
        # Skip looks that already have explicit fingerprint ranges
        if look.dominant_elements and look.activity_range is not None:
            continue

        # Find the primary section for defaults
        primary_section = look.sections[0] if look.sections else "verse"
        defaults = _SECTION_FINGERPRINT_DEFAULTS.get(primary_section, {})

        # Apply section defaults for missing fields
        if not look.dominant_elements:
            look.dominant_elements = list(defaults.get("dominant_elements", []))
        if look.activity_range is None:
            look.activity_range = defaults.get("activity_range")
        if look.density_range is None:
            look.density_range = defaults.get("density_range")
        if look.ambiance_range is None:
            look.ambiance_range = defaults.get("ambiance_range")
        if look.drive_range is None:
            look.drive_range = defaults.get("drive_range")
        if not look.texture_labels:
            look.texture_labels = list(defaults.get("texture_labels", []))

        # Apply audio character tweaks (override section defaults where specific)
        for char in look.audio_characters:
            tweaks = _AUDIO_CHAR_TWEAKS.get(char, {})
            for key, value in tweaks.items():
                if key == "dominant_elements":
                    # Merge, don't replace — add the character-specific elements
                    for elem in value:
                        if elem not in look.dominant_elements:
                            look.dominant_elements.insert(0, elem)
                elif key == "texture_labels":
                    for label in value:
                        if label not in look.texture_labels:
                            look.texture_labels.append(label)
                else:
                    # For ranges, prefer the more specific (character) value
                    setattr(look, key, value)

# Run auto-tagging on module load
_auto_tag_looks()


# ══════════════════════════════════════════════════════════════════════
#  AUDIO CHARACTER CLASSIFIER
# ══════════════════════════════════════════════════════════════════════

def classify_audio_character(audio_intel_state) -> List[str]:
    """Classify current audio into character tags from AudioIntelligence state.

    Returns a list of matching character tags for look selection.
    """
    if audio_intel_state is None:
        return []

    tags = []
    timbre = audio_intel_state.timbre
    rhythm = audio_intel_state.rhythm
    events = audio_intel_state.events
    traj = audio_intel_state.trajectory

    # Fast transients: high onset density or active high-energy transients
    if timbre.density > 0.6 and timbre.brightness > 0.45:
        tags.append("fast_transients")

    # Heavy bass: warm timbre + high current energy in bass range
    if timbre.warmth > 0.6 and traj.current > 0.4:
        tags.append("heavy_bass")

    # Synth lead: bright + melodic (not too noisy) + moderate-high energy
    if timbre.brightness > 0.5 and timbre.noisiness < 0.5 and traj.current > 0.3:
        tags.append("synth_lead")

    # Drum breakdown: rhythmic but sparse, high onset regularity
    if rhythm.groove_intensity > 0.4 and timbre.density < 0.5 and traj.current < 0.55:
        tags.append("drum_breakdown")

    # Sparse ambient: low density + low energy
    if timbre.density < 0.25 and traj.current < 0.2:
        tags.append("sparse_ambient")

    # Noise riser: active riser event
    if any(e.event_type == "riser" for e in events):
        tags.append("noise_riser")

    # Percussive: high groove + regular kicks
    if rhythm.groove_intensity > 0.5 and rhythm.onset_regularity > 0.4:
        tags.append("percussive")

    # Filtered: active sweep events
    if any(e.event_type.startswith("sweep") for e in events):
        tags.append("filtered")

    # Impact: active impact or drop_hit event
    if any(e.event_type in ("impact", "drop_hit") for e in events):
        tags.append("impact")

    # Full wall: high density + high energy + high groove
    if timbre.density > 0.6 and traj.current > 0.6 and rhythm.groove_intensity > 0.5:
        tags.append("full_wall")

    # Vocal heavy: detected from vocal analyzer (checked externally)
    # This tag is added by the effects engine when vocal cadence is active

    return tags


class LookSelector:
    """Selects looks using DISTANCE-BASED matching against musical fingerprints.

    Instead of hard rules, computes how well each look's fingerprint ranges
    match the current MusicalFingerprint. Closer match = higher weight.
    Still uses weighted random selection for variety — the same musical
    moment can produce different (but always appropriate) looks.

    MATCHING LAYERS (in priority order):
    1. Section filter: must match (hard gate)
    2. Energy range: must match (hard gate)
    3. Musical fingerprint distance: continuous scoring (soft — closer = better)
    4. Mood match: bonus weight
    5. Audio character match: bonus weight (legacy, still useful)
    6. RNG weighted selection from scored candidates
    """

    def __init__(self):
        self._current_look: Optional[LookPreset] = None
        self._look_hold_until_bar: int = 0
        self._look_history: list = []  # last N looks (avoid immediate repeats)
        self._history_size: int = 4
        self._rng = random.Random()
        self._rng.seed(42)

    def select_look(self, section: str, energy: float, mood: str,
                    bar_clock: int, force_new: bool = False,
                    audio_characters: List[str] = None,
                    musical_fingerprint=None) -> Optional[LookPreset]:
        """Select a look from the library matching current criteria.

        Args:
            section: Current section (breakdown/verse/buildup/chorus/drop)
            energy: Current energy level (0-1)
            mood: Current mood string
            bar_clock: Current bar number
            force_new: Force selection of a new look
            audio_characters: Current audio character tags from AudioIntelligence
            musical_fingerprint: MusicalFingerprint from MusicalIntelligence (NEW)

        Returns:
            LookPreset if a new look was selected, None if holding current
        """
        if audio_characters is None:
            audio_characters = []

        # Check hold timer
        if not force_new and self._current_look is not None:
            if bar_clock < self._look_hold_until_bar:
                return None

        # Find all compatible looks with fingerprint-based scoring
        candidates = []
        for look in LOOK_LIBRARY:
            # ── Hard gates ──
            if section not in look.sections:
                continue
            if energy < look.energy_min or energy > look.energy_max:
                continue
            if look.name in self._look_history:
                continue

            # ── Fingerprint distance scoring (the new core) ──
            fingerprint_score = 1.0
            if musical_fingerprint is not None:
                fingerprint_score = self._compute_fingerprint_match(
                    look, musical_fingerprint
                )

            # ── Legacy scoring (mood + audio character) ──
            mood_bonus = 1.0
            if mood and mood in look.moods:
                mood_bonus = 1.8

            char_bonus = 1.0
            if audio_characters and look.audio_characters:
                char_matches = sum(1 for c in audio_characters if c in look.audio_characters)
                if char_matches > 0:
                    char_bonus = 1.0 + char_matches * 0.4
                else:
                    char_bonus = 0.6

            # Combined weight: fingerprint is primary, mood/char are bonuses
            weight = look.weight * fingerprint_score * mood_bonus * char_bonus
            candidates.append((look, weight))

        if not candidates:
            # Fallback: relax all soft constraints, keep section + energy
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
        if total_weight <= 0:
            return None
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
        self._look_hold_until_bar = bar_clock + 8
        self._look_history.append(selected.name)
        if len(self._look_history) > self._history_size:
            self._look_history.pop(0)

        return selected

    def _compute_fingerprint_match(self, look: LookPreset, fp) -> float:
        """Compute how well a look's fingerprint ranges match the current moment.

        Returns a score from 0.1 (poor match) to 3.0 (excellent match).
        Uses distance-to-range for continuous dimensions and set overlap
        for categorical dimensions.

        The key insight: this is NOT binary. A look that's slightly outside
        its ideal range still gets a decent score, just lower. No cliff edges.
        """
        score = 1.0
        dimension_count = 0

        # ── Dominant element match ──
        if look.dominant_elements and hasattr(fp, 'dominant'):
            dimension_count += 1
            dom = fp.dominant
            # Check if the current dominant element matches any of the look's preferred elements
            current_dominant = dom.label
            if current_dominant in look.dominant_elements:
                # Direct match: big bonus scaled by how dominant it is
                dominance = dom.dominant_score()
                score *= 1.0 + dominance * 1.5  # up to 2.5x for strong match
            else:
                # Check if any of the look's elements have significant score
                element_scores = {
                    "bass_synth": dom.bass_synth,
                    "lead_synth": dom.lead_synth,
                    "pad": dom.pad,
                    "drums": dom.drums,
                    "vocal": dom.vocal,
                    "noise": dom.noise,
                }
                best_match = max(
                    (element_scores.get(e, 0.0) for e in look.dominant_elements),
                    default=0.0
                )
                # Partial match: element is present but not dominant
                score *= 0.4 + best_match * 0.6  # 0.4 to 1.0

        # ── Continuous dimension matches ──
        range_checks = [
            (look.activity_range, fp.element_activity if hasattr(fp, 'element_activity') else None),
            (look.density_range, fp.density if hasattr(fp, 'density') else None),
            (look.ambiance_range, fp.ambiance if hasattr(fp, 'ambiance') else None),
            (look.drive_range, fp.drive if hasattr(fp, 'drive') else None),
        ]

        for range_spec, value in range_checks:
            if range_spec is None or value is None:
                continue
            dimension_count += 1
            lo, hi = range_spec
            if lo <= value <= hi:
                # Inside range: bonus (centered = best)
                center = (lo + hi) / 2.0
                half_width = (hi - lo) / 2.0 + 0.01
                closeness = 1.0 - abs(value - center) / half_width
                score *= 1.0 + closeness * 0.5  # 1.0 to 1.5x
            else:
                # Outside range: penalty based on distance
                if value < lo:
                    dist = lo - value
                else:
                    dist = value - hi
                # Soft penalty: nearby is ok, far is bad
                penalty = max(0.2, 1.0 - dist * 3.0)
                score *= penalty

        # ── Texture label match ──
        if look.texture_labels and hasattr(fp, 'texture_label'):
            dimension_count += 1
            if fp.texture_label in look.texture_labels:
                score *= 1.3
            else:
                score *= 0.7

        # Normalize: more matching dimensions = more confident score
        # Avoid over-penalizing looks with few dimensions specified
        if dimension_count == 0:
            return 1.0  # no fingerprint data, neutral

        return max(0.1, score)

    @property
    def current(self) -> Optional[LookPreset]:
        return self._current_look
