"""
Gobo Choreography Engine
========================

Section-aware gobo selection and rotation for natural beam texturing.
Mimics how a human LD uses gobos:
- Open beam for breakdowns and soft moments
- Textured gobos for verses to add visual interest without overwhelming
- Rotating gobos during buildups for tension
- Sharp/fast gobos on drops for maximum impact
- Smooth transitions between gobo states (no harsh snapping)
"""

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class GoboMode(Enum):
    """High-level gobo intent modes."""
    OPEN = "open"               # No gobo - clean beam
    TEXTURE_SLOW = "texture_slow"   # Slow-rotating textured gobo (verse/ambient)
    TEXTURE_FAST = "texture_fast"   # Fast-rotating textured gobo (chorus/high energy)
    BREAKUP = "breakup"         # Breakup pattern (creates interesting floor/wall patterns)
    SHARP = "sharp"             # Sharp static gobo (drops, precise looks)
    AERIAL = "aerial"           # Mid-air beam texture (light shows, EDM)
    PRISM_WASH = "prism_wash"   # Prism + slow gobo for wash effect


# Gobo slot assignments (normalized 0-1, maps to fixture's gobo wheel)
# 0.0 = open, 0.1-0.9 = gobo patterns, arranged by visual density
GOBO_SLOTS = {
    "open": 0.0,
    "dots": 0.12,           # Scattered dots/circles
    "star": 0.22,           # Star/radial pattern
    "spiral": 0.32,         # Spiral pattern
    "breakup_organic": 0.42,  # Organic breakup (branches/leaves)
    "lines": 0.52,          # Parallel lines
    "grid": 0.62,           # Grid/crosshatch
    "circle_breakup": 0.72, # Broken circle
    "sharp_cone": 0.82,     # Sharp cone/triangle
    "tight_spot": 0.92,     # Very tight beam reducer
}

# Section -> gobo mode mapping (what a human LD would typically do)
SECTION_GOBO_POLICY = {
    "intro": GoboMode.TEXTURE_SLOW,
    "verse": GoboMode.TEXTURE_SLOW,
    "chorus": GoboMode.TEXTURE_FAST,
    "buildup": GoboMode.BREAKUP,
    "drop": GoboMode.SHARP,
    "breakdown": GoboMode.OPEN,
    "bridge": GoboMode.TEXTURE_SLOW,
    "outro": GoboMode.OPEN,
    "peak": GoboMode.AERIAL,
}

# Which gobo slots each mode prefers
MODE_GOBO_POOL = {
    GoboMode.OPEN: ["open"],
    GoboMode.TEXTURE_SLOW: ["dots", "spiral", "breakup_organic"],
    GoboMode.TEXTURE_FAST: ["star", "lines", "circle_breakup"],
    GoboMode.BREAKUP: ["breakup_organic", "circle_breakup", "dots"],
    GoboMode.SHARP: ["sharp_cone", "tight_spot", "grid"],
    GoboMode.AERIAL: ["star", "spiral", "lines"],
    GoboMode.PRISM_WASH: ["dots", "spiral"],
}


@dataclass
class GoboState:
    """Per-fixture gobo state for smooth transitions."""
    current_index: float = 0.0
    target_index: float = 0.0
    current_rotation: float = 0.0
    target_rotation_speed: float = 0.0
    current_zoom: float = 0.5
    target_zoom: float = 0.5
    current_iris: float = 1.0
    target_iris: float = 1.0
    current_frost: float = 0.0
    target_frost: float = 0.0
    current_prism: float = 0.0
    target_prism: float = 0.0


class GoboEngine:
    """
    Musically-aware gobo controller that mimics human LD gobo use.

    Key behaviors:
    - Gobos change on musical boundaries (phrase starts, section changes)
    - Rotation speed follows energy/BPM
    - Smooth mechanical transitions (gobos don't snap instantly on real fixtures)
    - Fixture-type awareness (beams get sharper gobos, spots get texture)
    - Odd/even fixture variation (not every fixture has the same gobo)
    """

    def __init__(self):
        self.time = 0.0
        self._fixture_states: Dict[str, GoboState] = {}
        self._current_mode: GoboMode = GoboMode.OPEN
        self._current_section: str = "__uninitialized__"  # Force first update to trigger mode set
        self._last_gobo_change_time: float = -999.0
        self._gobo_hold_bars: int = 4  # Minimum bars before gobo change
        self._selected_gobo_a: str = "open"  # For odd fixtures
        self._selected_gobo_b: str = "open"  # For even fixtures
        self._rotation_base_speed: float = 0.0
        self._bar_clock: int = 0
        self._needs_target_refresh: bool = True  # Ensure new fixtures get correct targets

    def update(self, delta_time: float, bpm: float = 128.0,
               energy: float = 0.5, bass: float = 0.5,
               section: str = "verse", bar_clock: int = 0,
               beat_phase: float = 0.0):
        """Update gobo engine state each frame."""
        self.time += delta_time
        self._bar_clock = bar_clock

        # Section change triggers gobo mode update
        if section != self._current_section:
            self._current_section = section
            self._update_gobo_mode(section, energy)

        # Periodic gobo rotation within same section (every N bars)
        if bar_clock > 0 and bar_clock % self._gobo_hold_bars == 0:
            if self.time - self._last_gobo_change_time > 2.0:
                self._rotate_gobo_selection()

        # Update rotation speed based on energy and BPM
        self._update_rotation_speed(bpm, energy, section, beat_phase)

        # Smooth all fixture states toward targets
        for fid, state in self._fixture_states.items():
            self._smooth_state(state, delta_time, section)

    def _update_gobo_mode(self, section: str, energy: float):
        """Select gobo mode based on section (like a human LD would).

        Section policy always takes priority for gobo selection.
        Energy modulates intensity/rotation within the chosen mode,
        not whether a gobo is used at all.
        """
        section_lower = section.lower()
        new_mode = SECTION_GOBO_POLICY.get(section_lower, GoboMode.TEXTURE_SLOW)

        if new_mode != self._current_mode:
            self._current_mode = new_mode
            self._select_gobos_for_mode(new_mode)
            self._last_gobo_change_time = self.time

    def _select_gobos_for_mode(self, mode: GoboMode):
        """Pick gobo slots for current mode (A/B for fixture variation)."""
        pool = MODE_GOBO_POOL.get(mode, ["open"])
        if len(pool) >= 2:
            self._selected_gobo_a = pool[0]
            self._selected_gobo_b = pool[1]
        elif pool:
            self._selected_gobo_a = pool[0]
            self._selected_gobo_b = pool[0]

        # Set targets for all fixtures
        for fid, state in self._fixture_states.items():
            idx = hash(fid) % 2
            gobo_name = self._selected_gobo_a if idx == 0 else self._selected_gobo_b
            state.target_index = GOBO_SLOTS.get(gobo_name, 0.0)

        # Update zoom/iris/frost targets based on mode
        self._update_optics_targets(mode)

    def _update_optics_targets(self, mode: GoboMode):
        """Set zoom, iris, frost, prism targets based on gobo mode."""
        section = self._current_section.lower()

        # Zoom: narrow for drops/sharp, wide for breakdowns/open
        zoom_map = {
            GoboMode.OPEN: 0.65,
            GoboMode.TEXTURE_SLOW: 0.45,
            GoboMode.TEXTURE_FAST: 0.35,
            GoboMode.BREAKUP: 0.50,
            GoboMode.SHARP: 0.15,
            GoboMode.AERIAL: 0.25,
            GoboMode.PRISM_WASH: 0.70,
        }
        # Iris: tighter for impact, open for ambience
        iris_map = {
            GoboMode.OPEN: 1.0,
            GoboMode.TEXTURE_SLOW: 0.85,
            GoboMode.TEXTURE_FAST: 0.70,
            GoboMode.BREAKUP: 0.75,
            GoboMode.SHARP: 0.40,
            GoboMode.AERIAL: 0.55,
            GoboMode.PRISM_WASH: 0.90,
        }
        # Frost: more for washes/breakdowns, none for sharp
        frost_map = {
            GoboMode.OPEN: 0.30 if section == "breakdown" else 0.05,
            GoboMode.TEXTURE_SLOW: 0.15,
            GoboMode.TEXTURE_FAST: 0.05,
            GoboMode.BREAKUP: 0.20,
            GoboMode.SHARP: 0.0,
            GoboMode.AERIAL: 0.0,
            GoboMode.PRISM_WASH: 0.40,
        }
        # Prism: only for aerial/wash modes
        prism_map = {
            GoboMode.OPEN: 0.0,
            GoboMode.TEXTURE_SLOW: 0.0,
            GoboMode.TEXTURE_FAST: 0.0,
            GoboMode.BREAKUP: 0.0,
            GoboMode.SHARP: 0.0,
            GoboMode.AERIAL: 0.6,
            GoboMode.PRISM_WASH: 0.8,
        }

        for fid, state in self._fixture_states.items():
            state.target_zoom = zoom_map.get(mode, 0.5)
            state.target_iris = iris_map.get(mode, 1.0)
            state.target_frost = frost_map.get(mode, 0.0)
            state.target_prism = prism_map.get(mode, 0.0)

    def _rotate_gobo_selection(self):
        """Rotate gobo selection within current mode's pool (adds variety)."""
        pool = MODE_GOBO_POOL.get(self._current_mode, ["open"])
        if len(pool) <= 1:
            return

        # Shift selections forward in pool
        old_a = self._selected_gobo_a
        pool_idx_a = pool.index(old_a) if old_a in pool else 0
        pool_idx_b = (pool_idx_a + 1) % len(pool)
        self._selected_gobo_a = pool[pool_idx_b]
        self._selected_gobo_b = pool[(pool_idx_b + 1) % len(pool)]
        self._last_gobo_change_time = self.time

        for fid, state in self._fixture_states.items():
            idx = hash(fid) % 2
            gobo_name = self._selected_gobo_a if idx == 0 else self._selected_gobo_b
            state.target_index = GOBO_SLOTS.get(gobo_name, 0.0)

    def _update_rotation_speed(self, bpm: float, energy: float,
                                section: str, beat_phase: float):
        """Update gobo rotation speed - human LDs sync rotation to music feel."""
        section_lower = section.lower()

        # Base rotation speed from BPM (one full rotation per N beats)
        beats_per_rotation = {
            "breakdown": 16.0,   # Very slow breathing rotation
            "verse": 8.0,        # Gentle rotation
            "intro": 12.0,
            "bridge": 10.0,
            "chorus": 4.0,       # Noticeable rotation
            "buildup": 2.0,      # Accelerating rotation
            "drop": 1.0,         # Fast rotation
            "peak": 0.5,         # Very fast
            "outro": 16.0,
        }
        bpr = beats_per_rotation.get(section_lower, 8.0)

        # Convert to rotation speed (0-1 per second)
        if bpr > 0:
            rotation_hz = (bpm / 60.0) / bpr
        else:
            rotation_hz = 0.0

        # Energy modulates rotation speed (+/- 30%)
        energy_mod = 0.7 + energy * 0.6
        self._rotation_base_speed = rotation_hz * energy_mod

        # Buildup acceleration: rotation speeds up as buildup progresses
        if section_lower == "buildup":
            # Use beat_phase as a proxy for buildup progress
            self._rotation_base_speed *= (1.0 + beat_phase * 1.5)

        for fid, state in self._fixture_states.items():
            state.target_rotation_speed = self._rotation_base_speed

    def _smooth_state(self, state: GoboState, delta_time: float, section: str):
        """Smooth all gobo parameters toward targets (mechanical realism).

        Real moving heads reach zoom/iris targets in ~0.5-2 seconds.
        Uses exponential smoothing with snapping when close to target.
        """
        section_lower = section.lower()
        # Clamp delta_time to prevent huge jumps after pauses
        dt = min(delta_time, 0.1)

        # Gobo wheel change speed: real gobo wheels take ~200-500ms to change
        gobo_speed = 8.0 if section_lower in {"drop", "peak"} else 5.0
        diff = state.target_index - state.current_index
        if abs(diff) > 0.005:
            state.current_index += diff * min(1.0, gobo_speed * dt)
        else:
            state.current_index = state.target_index

        # Rotation: accumulate rotation angle
        state.current_rotation += state.target_rotation_speed * dt
        state.current_rotation %= 1.0  # Wrap

        # Zoom smooth (zoom motors are fast on modern fixtures, ~0.5-1s)
        zoom_speed = 12.0
        zdiff = state.target_zoom - state.current_zoom
        if abs(zdiff) > 0.005:
            state.current_zoom += zdiff * min(1.0, zoom_speed * dt)
        else:
            state.current_zoom = state.target_zoom

        # Iris smooth (iris is mechanical, ~0.5-1.5s)
        iris_speed = 10.0
        idiff = state.target_iris - state.current_iris
        if abs(idiff) > 0.005:
            state.current_iris += idiff * min(1.0, iris_speed * dt)
        else:
            state.current_iris = state.target_iris

        # Frost smooth (frost filter slides, ~1-2s)
        frost_speed = 6.0
        fdiff = state.target_frost - state.current_frost
        if abs(fdiff) > 0.005:
            state.current_frost += fdiff * min(1.0, frost_speed * dt)
        else:
            state.current_frost = state.target_frost

        # Prism (mechanical insert, snappy ~0.3s)
        prism_speed = 12.0
        pdiff = state.target_prism - state.current_prism
        if abs(pdiff) > 0.005:
            state.current_prism += pdiff * min(1.0, prism_speed * dt)
        else:
            state.current_prism = state.target_prism

    def get_fixture_state(self, fixture_id: str, fixture_index: int) -> GoboState:
        """Get or create gobo state for a fixture."""
        if fixture_id not in self._fixture_states:
            state = GoboState()
            # Initialize with current mode's gobo
            idx = fixture_index % 2
            gobo_name = self._selected_gobo_a if idx == 0 else self._selected_gobo_b
            state.current_index = GOBO_SLOTS.get(gobo_name, 0.0)
            state.target_index = state.current_index

            # Initialize zoom/iris/frost/prism targets from current mode
            zoom_map = {
                GoboMode.OPEN: 0.65, GoboMode.TEXTURE_SLOW: 0.45,
                GoboMode.TEXTURE_FAST: 0.35, GoboMode.BREAKUP: 0.50,
                GoboMode.SHARP: 0.15, GoboMode.AERIAL: 0.25, GoboMode.PRISM_WASH: 0.70,
            }
            iris_map = {
                GoboMode.OPEN: 1.0, GoboMode.TEXTURE_SLOW: 0.85,
                GoboMode.TEXTURE_FAST: 0.70, GoboMode.BREAKUP: 0.75,
                GoboMode.SHARP: 0.40, GoboMode.AERIAL: 0.55, GoboMode.PRISM_WASH: 0.90,
            }
            state.target_zoom = zoom_map.get(self._current_mode, 0.5)
            state.target_iris = iris_map.get(self._current_mode, 1.0)
            # Start at the target values so there's no jarring snap from defaults
            state.current_zoom = state.target_zoom
            state.current_iris = state.target_iris

            self._fixture_states[fixture_id] = state
        return self._fixture_states[fixture_id]

    def apply_to_fixture(self, fixture, fixture_index: int, energy: float = 0.5,
                          bass: float = 0.5, beat_phase: float = 0.0):
        """Apply gobo engine state to a fixture object."""
        state = self.get_fixture_state(fixture.id, fixture_index)

        fixture.gobo_index = max(0.0, min(1.0, state.current_index))
        fixture.gobo_rotation = max(0.0, min(1.0, state.current_rotation))
        fixture.zoom = max(0.0, min(1.0, state.current_zoom))
        fixture.iris = max(0.0, min(1.0, state.current_iris))
        fixture.frost = max(0.0, min(1.0, state.current_frost))
        fixture.prism = max(0.0, min(1.0, state.current_prism))

        # Beat-reactive iris pulse: slight iris close on bass hits
        if bass > 0.65:
            bass_pulse = (bass - 0.65) / 0.35
            iris_punch = 0.12 * bass_pulse * (0.5 + 0.5 * math.sin(beat_phase * math.pi * 2))
            fixture.iris = max(0.1, fixture.iris - iris_punch)

        # Energy-reactive zoom breathing
        if self._current_section.lower() in {"verse", "breakdown", "bridge"}:
            zoom_breath = 0.06 * math.sin(self.time * 0.3) * (1.0 - energy)
            fixture.zoom = max(0.0, min(1.0, fixture.zoom + zoom_breath))
