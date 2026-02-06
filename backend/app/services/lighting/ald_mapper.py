"""
ALD-to-DMX Mapper
=================

Maps Abstract Lighting Description (ALD) states to concrete DMX values
for a specific rig configuration. This is the bridge between the
rig-agnostic AI output and the fixture-specific DMX protocol.

Key responsibilities:
1. Zone assignment: map fixtures to stage zones based on position
2. Fixture count normalization: scale ALD for any number of fixtures
3. Color conversion: ALD HSB -> fixture RGB/CMY/color wheel DMX
4. Movement conversion: abstract movement -> pan/tilt DMX values
5. Effect mapping: abstract effects -> DMX channel patterns
"""

import math
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging

from app.models.ald import (
    AbstractLightingState,
    ALDZoneState,
    ALDColor,
    StageZone,
    ZONE_POSITIONS,
    MovementType,
    EffectType,
)

logger = logging.getLogger(__name__)


@dataclass
class FixtureZoneAssignment:
    """A fixture assigned to a stage zone with spatial weight."""
    fixture_id: str
    zone: StageZone
    weight: float = 1.0           # How strongly this fixture represents the zone
    position: Tuple[float, float] = (0.5, 0.5)  # Normalized (x, y) position
    has_color: bool = True
    has_movement: bool = False
    has_dimmer: bool = True


@dataclass
class DMXFixtureOutput:
    """DMX output values for a single fixture."""
    fixture_id: str
    dimmer: int = 0                # 0-255
    red: int = 0                   # 0-255
    green: int = 0                 # 0-255
    blue: int = 0                  # 0-255
    white: int = 0                 # 0-255 (if fixture has W channel)
    pan: int = 128                 # 0-255
    tilt: int = 128                # 0-255
    pan_fine: int = 0              # 0-255
    tilt_fine: int = 0             # 0-255
    strobe: int = 0                # 0-255
    gobo: int = 0                  # 0-255
    focus: int = 128               # 0-255


class ALDMapper:
    """Maps ALD states to DMX values for a specific rig.

    Usage:
        mapper = ALDMapper()
        mapper.configure_rig(fixtures)
        dmx_output = mapper.map_state(ald_state)
    """

    def __init__(self):
        self._fixtures: Dict[str, FixtureZoneAssignment] = {}
        self._zone_fixtures: Dict[StageZone, List[str]] = {
            zone: [] for zone in StageZone
        }
        self._fixture_count = 0
        self._time = 0.0

    def configure_rig(self, fixtures: List[Dict[str, Any]]):
        """Configure the rig with fixture positions and capabilities.

        Args:
            fixtures: List of fixture configs with at minimum:
                {id, x, y, type, has_color, has_movement, has_dimmer}
                x, y are normalized 0-1 stage positions
        """
        self._fixtures.clear()
        for zone in StageZone:
            self._zone_fixtures[zone] = []

        for f in fixtures:
            fid = str(f.get("id", f.get("fixture_id", "")))
            x = float(f.get("x", f.get("position_x", 0.5)))
            y = float(f.get("y", f.get("position_y", 0.5)))

            zone = self._position_to_zone(x, y)
            weight = self._zone_weight(x, y, zone)

            assignment = FixtureZoneAssignment(
                fixture_id=fid,
                zone=zone,
                weight=weight,
                position=(x, y),
                has_color=f.get("has_color", True),
                has_movement=f.get("has_movement", f.get("type", "") in ("moving_head", "spot")),
                has_dimmer=f.get("has_dimmer", True),
            )

            self._fixtures[fid] = assignment
            self._zone_fixtures[zone].append(fid)
            self._zone_fixtures[StageZone.ALL].append(fid)

        self._fixture_count = len(self._fixtures)
        logger.info(
            "Rig configured: %d fixtures across %d zones",
            self._fixture_count,
            sum(1 for z, fids in self._zone_fixtures.items() if fids and z != StageZone.ALL),
        )

    def map_state(
        self,
        state: AbstractLightingState,
        beat_phase: float = 0.0,
        is_beat: bool = False,
        dt: float = 0.025,
    ) -> List[DMXFixtureOutput]:
        """Map an ALD state to DMX values for all fixtures.

        Args:
            state: The abstract lighting state to map
            beat_phase: Current position within beat (0-1)
            is_beat: Whether a beat is occurring this frame
            dt: Time delta since last frame (seconds)

        Returns:
            List of DMX output values, one per fixture
        """
        self._time += dt
        outputs = []

        for fid, assignment in self._fixtures.items():
            output = self._map_single_fixture(
                state, assignment, beat_phase, is_beat
            )
            outputs.append(output)

        return outputs

    def _map_single_fixture(
        self,
        state: AbstractLightingState,
        assignment: FixtureZoneAssignment,
        beat_phase: float,
        is_beat: bool,
    ) -> DMXFixtureOutput:
        """Map ALD state to a single fixture's DMX values."""
        output = DMXFixtureOutput(fixture_id=assignment.fixture_id)

        # Find zone state for this fixture
        zone_state = self._get_zone_state(state, assignment.zone)

        # --- Intensity ---
        base_intensity = state.master_intensity
        if zone_state:
            base_intensity *= zone_state.intensity
        else:
            base_intensity *= state.energy_level

        # Coverage scaling: fixtures further from focus get less light
        coverage_factor = self._coverage_factor(
            assignment, state.focus_zone, state.coverage
        )
        base_intensity *= coverage_factor

        # Beat pulse
        if state.pulse_depth > 0 and state.beat_response > 0:
            pulse = self._beat_pulse(beat_phase, state.pulse_depth, state.beat_response)
            base_intensity *= (1.0 - state.pulse_depth + pulse * state.pulse_depth)

        output.dimmer = int(max(0, min(255, base_intensity * 255)))

        # --- Color ---
        if assignment.has_color:
            color = self._resolve_color(state, zone_state, assignment)
            r, g, b = color.rgb
            output.red = int(max(0, min(255, r * 255)))
            output.green = int(max(0, min(255, g * 255)))
            output.blue = int(max(0, min(255, b * 255)))

        # --- Movement ---
        if assignment.has_movement:
            pan, tilt = self._resolve_movement(
                state, assignment, self._time
            )
            output.pan = int(max(0, min(255, pan)))
            output.tilt = int(max(0, min(255, tilt)))

        # --- Effects ---
        self._apply_effects(output, state, assignment, is_beat, beat_phase)

        return output

    def _get_zone_state(
        self, state: AbstractLightingState, zone: StageZone
    ) -> Optional[ALDZoneState]:
        """Find the zone state for a specific zone."""
        for zs in state.zones:
            if zs.zone == zone or zs.zone == StageZone.ALL:
                return zs
        return None

    def _coverage_factor(
        self,
        assignment: FixtureZoneAssignment,
        focus_zone: StageZone,
        coverage: float,
    ) -> float:
        """Calculate intensity factor based on coverage and focus.

        coverage=0: only fixtures in focus zone lit
        coverage=1: all fixtures equally lit
        """
        if coverage >= 1.0:
            return 1.0

        focus_pos = ZONE_POSITIONS.get(focus_zone, (0.5, 0.5))
        dx = assignment.position[0] - focus_pos[0]
        dy = assignment.position[1] - focus_pos[1]
        distance = math.sqrt(dx * dx + dy * dy)

        # Wider coverage means larger radius
        radius = coverage * 1.5  # At coverage=1, radius covers entire stage
        if radius <= 0:
            radius = 0.05

        if distance <= radius:
            return 1.0
        else:
            falloff = max(0.0, 1.0 - (distance - radius) / (1.0 - radius + 0.01))
            return falloff * falloff  # Quadratic falloff

    def _beat_pulse(
        self, beat_phase: float, depth: float, response: float
    ) -> float:
        """Calculate beat pulse intensity.

        Returns 1.0 on beat, decays to 0.0 between beats.
        """
        # Sharp attack, exponential decay
        pulse = max(0.0, 1.0 - beat_phase * 3.0) * response
        return max(0.0, min(1.0, pulse))

    def _resolve_color(
        self,
        state: AbstractLightingState,
        zone_state: Optional[ALDZoneState],
        assignment: FixtureZoneAssignment,
    ) -> ALDColor:
        """Resolve the color for a fixture."""
        if zone_state and zone_state.color:
            return zone_state.color

        # Use primary/secondary based on fixture position for variation
        if assignment.position[0] < 0.5:
            return state.primary_color
        else:
            return state.secondary_color

    def _resolve_movement(
        self,
        state: AbstractLightingState,
        assignment: FixtureZoneAssignment,
        time: float,
    ) -> Tuple[float, float]:
        """Calculate pan/tilt DMX values from abstract movement.

        Returns (pan, tilt) in 0-255 range.
        """
        movement = state.movement
        mt = movement.movement_type
        speed = movement.speed
        size = movement.size * 64  # Scale to half DMX range
        phase = movement.phase_offset

        # Base position (center)
        base_pan = 128.0
        base_tilt = 128.0

        # Fixture-specific phase offset (distribute across fixtures)
        fixture_idx = list(self._fixtures.keys()).index(assignment.fixture_id) \
            if assignment.fixture_id in self._fixtures else 0
        fixture_phase = (fixture_idx / max(1, self._fixture_count)) * phase

        t = time * speed * 2 * math.pi + fixture_phase * 2 * math.pi

        if mt == MovementType.CIRCLE:
            pan_offset = math.sin(t) * size
            tilt_offset = math.cos(t) * size

        elif mt == MovementType.FIGURE_8:
            pan_offset = math.sin(t) * size
            tilt_offset = math.sin(2 * t) * size * 0.5

        elif mt == MovementType.SWEEP_LR:
            pan_offset = math.sin(t) * size
            tilt_offset = 0

        elif mt == MovementType.SWEEP_FB:
            pan_offset = 0
            tilt_offset = math.sin(t) * size

        elif mt == MovementType.CHASE_LR:
            # Sawtooth wave for sequential activation
            wave = (math.fmod(t / (2 * math.pi) + fixture_phase, 1.0)) * 2 - 1
            pan_offset = wave * size
            tilt_offset = 0

        elif mt == MovementType.CHASE_RL:
            wave = (math.fmod(-t / (2 * math.pi) + fixture_phase, 1.0)) * 2 - 1
            pan_offset = wave * size
            tilt_offset = 0

        elif mt == MovementType.CONVERGE:
            # All fixtures point toward center
            target_x, target_y = 0.5, 0.5
            dx = target_x - assignment.position[0]
            dy = target_y - assignment.position[1]
            anim = (1 + math.sin(t)) * 0.5  # 0 to 1
            pan_offset = dx * size * anim
            tilt_offset = dy * size * anim

        elif mt == MovementType.DIVERGE:
            dx = assignment.position[0] - 0.5
            dy = assignment.position[1] - 0.5
            anim = (1 + math.sin(t)) * 0.5
            pan_offset = dx * size * anim
            tilt_offset = dy * size * anim

        elif mt == MovementType.BALLYHOO:
            pan_offset = (math.sin(t) + math.sin(t * 1.7) * 0.5) * size * 0.7
            tilt_offset = (math.cos(t * 0.8) + math.cos(t * 2.3) * 0.3) * size * 0.5

        elif mt == MovementType.TILT_WAVE:
            wave_phase = fixture_phase * 2 * math.pi
            tilt_offset = math.sin(t + wave_phase) * size
            pan_offset = 0

        elif mt == MovementType.PAN_WAVE:
            wave_phase = fixture_phase * 2 * math.pi
            pan_offset = math.sin(t + wave_phase) * size
            tilt_offset = 0

        elif mt == MovementType.FOCUS_TRACK:
            if movement.focus_point:
                fx, fy = movement.focus_point
            else:
                fx, fy = 0.5, 0.5
            pan_offset = (fx - assignment.position[0]) * size * 2
            tilt_offset = (fy - assignment.position[1]) * size * 2

        else:  # NONE or RANDOM
            if mt == MovementType.RANDOM:
                # Gentle Perlin-like noise via multiple sine waves
                pan_offset = (
                    math.sin(t * 0.3 + fixture_phase * 5) * 0.5
                    + math.sin(t * 0.7 + fixture_phase * 3) * 0.3
                ) * size * 0.3
                tilt_offset = (
                    math.cos(t * 0.4 + fixture_phase * 4) * 0.5
                    + math.cos(t * 0.9 + fixture_phase * 2) * 0.3
                ) * size * 0.3
            else:
                pan_offset = 0
                tilt_offset = 0

        return (
            max(0, min(255, base_pan + pan_offset)),
            max(0, min(255, base_tilt + tilt_offset)),
        )

    def _apply_effects(
        self,
        output: DMXFixtureOutput,
        state: AbstractLightingState,
        assignment: FixtureZoneAssignment,
        is_beat: bool,
        beat_phase: float,
    ):
        """Apply active effects to fixture output."""
        for effect in state.effects:
            # Check if this fixture's zone is targeted
            if StageZone.ALL not in effect.zones and assignment.zone not in effect.zones:
                continue

            if effect.effect_type == EffectType.STROBE:
                # Strobe: rapid on/off
                strobe_speed = int(effect.speed * 200 + 20)  # 20-220 DMX range
                output.strobe = int(strobe_speed * effect.intensity)

            elif effect.effect_type == EffectType.BLACKOUT:
                output.dimmer = 0
                output.strobe = 0

            elif effect.effect_type == EffectType.FLASH:
                output.dimmer = 255
                output.red = 255
                output.green = 255
                output.blue = 255

            elif effect.effect_type == EffectType.PULSE:
                # Dimmer pulse on beats
                if is_beat:
                    output.dimmer = min(255, int(output.dimmer * (1 + effect.intensity)))

            elif effect.effect_type == EffectType.CHASE:
                # Sequential fixture activation
                fixture_idx = list(self._fixtures.keys()).index(assignment.fixture_id) \
                    if assignment.fixture_id in self._fixtures else 0
                chase_pos = (self._time * effect.speed * 2) % self._fixture_count
                distance = abs(fixture_idx - chase_pos)
                if distance > self._fixture_count / 2:
                    distance = self._fixture_count - distance
                chase_factor = max(0.0, 1.0 - distance / max(1, self._fixture_count * 0.3))
                output.dimmer = int(output.dimmer * chase_factor)

            elif effect.effect_type == EffectType.SPARKLE:
                # Random fixture flashes
                import random
                if random.random() < effect.speed * 0.1:
                    output.dimmer = min(255, output.dimmer + int(128 * effect.intensity))

    def _position_to_zone(self, x: float, y: float) -> StageZone:
        """Map a stage position to the nearest zone."""
        best_zone = StageZone.MSC
        best_dist = float("inf")

        for zone, (zx, zy) in ZONE_POSITIONS.items():
            if zone in (StageZone.ALL, StageZone.AUDIENCE):
                continue
            dx = x - zx
            dy = y - zy
            dist = dx * dx + dy * dy
            if dist < best_dist:
                best_dist = dist
                best_zone = zone

        return best_zone

    def _zone_weight(self, x: float, y: float, zone: StageZone) -> float:
        """Calculate how strongly a position represents its zone."""
        zx, zy = ZONE_POSITIONS.get(zone, (0.5, 0.5))
        dist = math.sqrt((x - zx) ** 2 + (y - zy) ** 2)
        return max(0.0, 1.0 - dist * 3)

    def get_fixture_zones(self) -> Dict[str, str]:
        """Get zone assignments for all fixtures."""
        return {
            fid: assignment.zone.value
            for fid, assignment in self._fixtures.items()
        }
