"""
Quick Rig Wizard Service
========================

Provides venue presets and automatic fixture placement for the
guided rig creation wizard.

Coordinate convention, shared with RigVisualizer and create_demo_rig:
    origin  centre of the stage floor
    X       across the stage, 0 at centre, [-width/2, +width/2]; side_left is -X
    Y       height above the deck, 0 at the deck
    Z       depth, 0 at centre, [-depth/2, +depth/2]; -Z is upstage / back wall,
            +Z is downstage, toward the audience

rotation_y is a yaw in degrees about +Y: 0 aims downstage (+Z), +90 aims toward +X.
That is Object3D.rotation.y for a model whose local forward is +Z.
"""

import logging
import math
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


# Where a fixture group is physically mounted. Supplied by the caller; never
# inferred from the group name the user typed.
MOUNTING_POSITIONS = (
    "front_truss",
    "mid_truss",
    "back_truss",
    "floor",
    "side_left",
    "side_right",
    "ceiling",
)

# axis   the axis fixtures of one group spread along
# z_frac line depth as a fraction of stage_depth (0 = stage centre)
# x_frac line offset across the stage as a fraction of stage_width (side mounts)
# y      ("drop", m) = stage_height - m, ("frac", f) = stage_height * f, ("abs", m)
#
# Ordered downstage to upstage: front_truss, ceiling, mid_truss, back_truss,
# floor. "ceiling" is the room's own ceiling, so it is the highest line, but it
# is overhead - putting it downstage of the front truss would hang the wash the
# templates call "overhead" out past the lip of the stage.
_MOUNT_LINES: Dict[str, Dict[str, Any]] = {
    "ceiling":     {"axis": "x", "z_frac":  0.10, "x_frac":  0.00, "y": ("drop", 0.0)},
    "front_truss": {"axis": "x", "z_frac":  0.35, "x_frac":  0.00, "y": ("drop", 0.5)},
    "mid_truss":   {"axis": "x", "z_frac":  0.00, "x_frac":  0.00, "y": ("drop", 0.75)},
    "back_truss":  {"axis": "x", "z_frac": -0.35, "x_frac":  0.00, "y": ("drop", 1.0)},
    "side_left":   {"axis": "z", "z_frac":  0.00, "x_frac": -0.48, "y": ("frac", 0.55)},
    "side_right":  {"axis": "z", "z_frac":  0.00, "x_frac":  0.48, "y": ("frac", 0.55)},
    "floor":       {"axis": "x", "z_frac": -0.42, "x_frac":  0.00, "y": ("abs", 0.2)},
}

# Used only when a caller omits mounting_position, so an un-migrated client still
# gets a sane rig. Keyed on fixture_type, which is a controlled vocabulary.
_DEFAULT_MOUNTING_BY_TYPE = {
    "led_par": "front_truss",
    "spot": "front_truss",
    "wash": "mid_truss",
    "moving_head": "mid_truss",
    "beam": "back_truss",
    "strobe": "back_truss",
    "laser": "back_truss",
    "led_bar": "floor",
    "effect": "ceiling",
}
_FALLBACK_MOUNTING = "mid_truss"

# Fixtures spread across this share of the stage, leaving room for the
# per-group interleave offset without leaving the deck.
_SPAN_FRACTION_WIDTH = 0.85
_SPAN_FRACTION_DEPTH = 0.60

# The area the rig is aimed at: the central strip of the stage at deck level.
_PERFORMANCE_HALF_WIDTH_FRACTION = 0.25


# Venue presets with suggested fixtures and stage dimensions
VENUE_PRESETS = {
    "small_club": {
        "name": "Small Club / Bar",
        "description": "Intimate venue, 50-200 capacity",
        "stage_width": 6.0,
        "stage_depth": 4.0,
        "stage_height": 3.5,
        "suggested_fixtures": [
            {"fixture_type": "led_par", "count": 6, "group_name": "Front Wash",
             "mounting_position": "front_truss"},
            {"fixture_type": "moving_head", "count": 2, "group_name": "Moving Heads",
             "mounting_position": "mid_truss"},
            {"fixture_type": "led_bar", "count": 2, "group_name": "LED Bars",
             "mounting_position": "floor"},
        ],
    },
    "medium_venue": {
        "name": "Medium Venue",
        "description": "Mid-size club or ballroom, 200-800 capacity",
        "stage_width": 10.0,
        "stage_depth": 8.0,
        "stage_height": 5.0,
        "suggested_fixtures": [
            {"fixture_type": "led_par", "count": 8, "group_name": "Front Wash",
             "mounting_position": "front_truss"},
            {"fixture_type": "moving_head", "count": 4, "group_name": "Moving Heads",
             "mounting_position": "mid_truss"},
            {"fixture_type": "led_bar", "count": 4, "group_name": "LED Bars",
             "mounting_position": "floor"},
            {"fixture_type": "wash", "count": 4, "group_name": "Washes",
             "mounting_position": "back_truss"},
        ],
    },
    "church": {
        "name": "House of Worship",
        "description": "Church or worship space, warm lighting",
        "stage_width": 12.0,
        "stage_depth": 6.0,
        "stage_height": 6.0,
        "suggested_fixtures": [
            {"fixture_type": "led_par", "count": 8, "group_name": "Front Wash",
             "mounting_position": "front_truss"},
            {"fixture_type": "wash", "count": 4, "group_name": "Stage Wash",
             "mounting_position": "mid_truss"},
            {"fixture_type": "spot", "count": 2, "group_name": "Key Light",
             "mounting_position": "front_truss"},
        ],
    },
    "theater": {
        "name": "Theater",
        "description": "Traditional theater or concert hall",
        "stage_width": 14.0,
        "stage_depth": 10.0,
        "stage_height": 8.0,
        "suggested_fixtures": [
            {"fixture_type": "spot", "count": 6, "group_name": "Front Spots",
             "mounting_position": "front_truss"},
            {"fixture_type": "wash", "count": 6, "group_name": "Stage Wash",
             "mounting_position": "mid_truss"},
            {"fixture_type": "moving_head", "count": 4, "group_name": "Moving Heads",
             "mounting_position": "back_truss"},
            {"fixture_type": "led_bar", "count": 4, "group_name": "Cyc Lights",
             "mounting_position": "floor"},
            {"fixture_type": "led_par", "count": 4, "group_name": "Side Wash Left",
             "mounting_position": "side_left"},
            {"fixture_type": "led_par", "count": 4, "group_name": "Side Wash Right",
             "mounting_position": "side_right"},
        ],
    },
    "festival_stage": {
        "name": "Festival Stage",
        "description": "Outdoor festival or large event stage",
        "stage_width": 18.0,
        "stage_depth": 12.0,
        "stage_height": 10.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 8, "group_name": "Moving Heads",
             "mounting_position": "mid_truss"},
            {"fixture_type": "wash", "count": 8, "group_name": "Washes",
             "mounting_position": "front_truss"},
            {"fixture_type": "led_bar", "count": 8, "group_name": "LED Bars",
             "mounting_position": "floor"},
            {"fixture_type": "strobe", "count": 4, "group_name": "Strobes",
             "mounting_position": "back_truss"},
            {"fixture_type": "beam", "count": 4, "group_name": "Beams",
             "mounting_position": "mid_truss"},
            {"fixture_type": "led_par", "count": 12, "group_name": "Front Wash",
             "mounting_position": "front_truss"},
        ],
    },
    "large_venue": {
        "name": "Large Venue / Arena",
        "description": "Concert arena or large indoor venue",
        "stage_width": 20.0,
        "stage_depth": 14.0,
        "stage_height": 12.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 12, "group_name": "Moving Heads",
             "mounting_position": "mid_truss"},
            {"fixture_type": "wash", "count": 10, "group_name": "Washes",
             "mounting_position": "front_truss"},
            {"fixture_type": "led_bar", "count": 10, "group_name": "LED Bars",
             "mounting_position": "floor"},
            {"fixture_type": "spot", "count": 6, "group_name": "Spots",
             "mounting_position": "ceiling"},
            {"fixture_type": "beam", "count": 6, "group_name": "Beams",
             "mounting_position": "back_truss"},
            {"fixture_type": "strobe", "count": 6, "group_name": "Strobes",
             "mounting_position": "back_truss"},
            {"fixture_type": "led_par", "count": 16, "group_name": "Front Wash",
             "mounting_position": "front_truss"},
        ],
    },
    "nightclub": {
        "name": "Nightclub",
        "description": "Dance club or DJ venue",
        "stage_width": 8.0,
        "stage_depth": 6.0,
        "stage_height": 4.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 4, "group_name": "Moving Heads",
             "mounting_position": "mid_truss"},
            {"fixture_type": "led_par", "count": 8, "group_name": "Wash",
             "mounting_position": "front_truss"},
            {"fixture_type": "led_bar", "count": 4, "group_name": "LED Bars",
             "mounting_position": "floor"},
            {"fixture_type": "strobe", "count": 2, "group_name": "Strobes",
             "mounting_position": "mid_truss"},
            {"fixture_type": "laser", "count": 2, "group_name": "Lasers",
             "mounting_position": "back_truss"},
            {"fixture_type": "effect", "count": 2, "group_name": "Effects",
             "mounting_position": "ceiling"},
        ],
    },
    "outdoor": {
        "name": "Outdoor Event",
        "description": "Outdoor concert or event space",
        "stage_width": 15.0,
        "stage_depth": 10.0,
        "stage_height": 8.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 6, "group_name": "Moving Heads",
             "mounting_position": "mid_truss"},
            {"fixture_type": "wash", "count": 6, "group_name": "Washes",
             "mounting_position": "front_truss"},
            {"fixture_type": "led_par", "count": 10, "group_name": "Front Wash",
             "mounting_position": "front_truss"},
            {"fixture_type": "led_bar", "count": 6, "group_name": "LED Bars",
             "mounting_position": "floor"},
            {"fixture_type": "beam", "count": 4, "group_name": "Beams",
             "mounting_position": "back_truss"},
        ],
    },
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _alternating(index: int) -> int:
    """0, +1, -1, +2, -2, ... so offsets stay centred on the base line."""
    return ((index + 1) // 2) * (1 if index % 2 else -1)


def _span_offset(i: int, count: int, span: float) -> float:
    """Position of the i-th of `count` fixtures spread evenly over `span`."""
    if count <= 1:
        return 0.0
    return -span / 2 + i * (span / (count - 1))


class WizardService:
    """Service for the quick rig setup wizard."""

    @staticmethod
    def get_venue_presets() -> List[Dict[str, Any]]:
        """Return all venue presets."""
        return [
            {"key": key, **preset}
            for key, preset in VENUE_PRESETS.items()
        ]

    @staticmethod
    def get_venue_preset(key: str) -> Optional[Dict[str, Any]]:
        """Get a specific venue preset."""
        preset = VENUE_PRESETS.get(key)
        if preset:
            return {"key": key, **preset}
        return None

    @staticmethod
    def get_mounting_positions() -> List[str]:
        """Return the mounting positions the wizard may ask the user to pick."""
        return list(MOUNTING_POSITIONS)

    @staticmethod
    def resolve_mounting_position(group: Dict[str, Any]) -> str:
        """Resolve a group's mounting position.

        An explicit `mounting_position` always wins. When the caller omits it we
        fall back to the fixture type, and finally to a mid truss. The group name
        is never consulted: renaming a group must not move its fixtures.

        Raises ValueError if an unrecognised mounting position is supplied.
        """
        declared = group.get("mounting_position")
        if declared:
            key = str(declared).strip().lower()
            if key not in MOUNTING_POSITIONS:
                raise ValueError(
                    f"Unknown mounting_position '{declared}'. "
                    f"Expected one of: {', '.join(MOUNTING_POSITIONS)}"
                )
            return key

        fixture_type = str(group.get("fixture_type") or "").strip().lower()
        return _DEFAULT_MOUNTING_BY_TYPE.get(fixture_type, _FALLBACK_MOUNTING)

    @staticmethod
    def compute_placement(
        stage_width: float,
        stage_depth: float,
        stage_height: float,
        fixtures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compute automatic fixture placement positions.

        Each fixture dict should have: fixture_id, count, group_name,
        mounting_position (optional), fixture_type (optional),
        mode_channel_count (optional).
        Returns list of placement dicts with position/addressing info.
        """
        placements = []
        dmx_address = 1
        universe = 0
        group_slots: Dict[str, int] = {}
        occupied: set = set()

        for group in fixtures:
            try:
                count = int(group.get("count", 1) or 1)
            except (TypeError, ValueError):
                count = 1
            count = max(count, 1)
            group_name = group.get("group_name") or "Default"
            fixture_id = group.get("fixture_id")
            mode_id = group.get("mode_id")
            channel_count = group.get("mode_channel_count", 16)

            mounting = WizardService.resolve_mounting_position(group)
            slot = group_slots.get(mounting, 0)
            group_slots[mounting] = slot + 1

            positions = WizardService._compute_group_positions(
                mounting, count, stage_width, stage_depth, stage_height, slot
            )

            for i, pos in enumerate(positions):
                # Check universe boundary
                if dmx_address + channel_count - 1 > 512:
                    universe += 1
                    dmx_address = 1

                x, y, z = WizardService._claim_position(
                    occupied, pos["x"], pos["y"], pos["z"], stage_depth
                )

                placements.append({
                    "fixture_id": fixture_id,
                    "mode_id": mode_id,
                    "name": f"{group_name} {i + 1}",
                    "group_name": group_name,
                    "mounting_position": mounting,
                    "universe": universe,
                    "dmx_address": dmx_address,
                    "position_x": x,
                    "position_y": y,
                    "position_z": z,
                    "rotation_y": WizardService._aim_rotation_y(x, z, stage_width),
                })

                dmx_address += channel_count

        return placements

    @staticmethod
    def _compute_group_positions(
        mounting_position: str,
        count: int,
        stage_width: float,
        stage_depth: float,
        stage_height: float,
        slot: int = 0,
    ) -> List[Dict[str, float]]:
        """Compute positions for one group on a mounting position.

        `slot` is how many earlier groups already occupy this mounting position.
        Groups sharing a mounting position are separated two ways: the line is
        staggered toward stage centre (in depth for truss/floor/ceiling lines, in
        width for side lines), and the fixtures along it are interleaved by an
        alternating phase offset so the two lines do not sit fixture-over-fixture.
        """
        line = _MOUNT_LINES[mounting_position]
        y = WizardService._mount_height(line["y"], stage_height)

        half_width = stage_width / 2
        half_depth = stage_depth / 2
        depth_step = min(0.6, stage_depth * 0.08)
        width_step = min(0.3, stage_width * 0.02)

        positions: List[Dict[str, float]] = []
        clamped = 0

        if line["axis"] == "x":
            raw_z = line["z_frac"] * stage_depth
            toward_centre = -1.0 if raw_z >= 0 else 1.0
            raw_z += toward_centre * slot * depth_step
            z = _clamp(raw_z, -half_depth, half_depth)
            if z != raw_z:
                clamped += 1
            span = stage_width * _SPAN_FRACTION_WIDTH
            phase = _alternating(slot) * width_step
            for i in range(count):
                raw_x = _span_offset(i, count, span) + phase
                x = _clamp(raw_x, -half_width, half_width)
                if x != raw_x:
                    clamped += 1
                positions.append({"x": round(x, 2), "y": round(y, 2), "z": round(z, 2)})
        else:
            raw_x = line["x_frac"] * stage_width
            toward_centre = -1.0 if raw_x >= 0 else 1.0
            raw_x += toward_centre * slot * width_step
            x = _clamp(raw_x, -half_width, half_width)
            if x != raw_x:
                clamped += 1
            span = stage_depth * _SPAN_FRACTION_DEPTH
            phase = _alternating(slot) * depth_step
            for i in range(count):
                raw_z = _span_offset(i, count, span) + phase
                z = _clamp(raw_z, -half_depth, half_depth)
                if z != raw_z:
                    clamped += 1
                positions.append({"x": round(x, 2), "y": round(y, 2), "z": round(z, 2)})

        # Clamping keeps fixtures on the deck but collapses them onto the edge,
        # so it is reported rather than applied silently.
        if clamped:
            logger.warning(
                "Mounting position %s slot %d does not fit a %.1f x %.1f stage; "
                "%d coordinate(s) clamped to the stage edge",
                mounting_position, slot, stage_width, stage_depth, clamped,
            )

        return positions

    @staticmethod
    def _mount_height(spec: Tuple[str, float], stage_height: float) -> float:
        """Resolve a mounting line's height spec against the stage trim height."""
        mode, value = spec
        if mode == "drop":
            height = stage_height - value
        elif mode == "frac":
            height = stage_height * value
        else:
            height = value
        return max(height, 0.2)

    @staticmethod
    def _aim_rotation_y(x: float, z: float, stage_width: float) -> float:
        """Yaw in degrees so the fixture faces the performance area.

        Each fixture aims at the nearest point of the central performance strip
        rather than all converging on stage centre, so a wash covers the stage
        instead of stacking on one spot.
        """
        performance_half_width = stage_width * _PERFORMANCE_HALF_WIDTH_FRACTION
        dx = _clamp(x, -performance_half_width, performance_half_width) - x
        dz = -z
        if abs(dx) < 1e-6 and abs(dz) < 1e-6:
            return 0.0
        return round(math.degrees(math.atan2(dx, dz)), 2)

    @staticmethod
    def _claim_position(
        occupied: set,
        x: float,
        y: float,
        z: float,
        stage_depth: float,
    ) -> Tuple[float, float, float]:
        """Reserve a position, walking toward stage centre if it is already taken.

        Two fixtures on the same point would render as one and are impossible to
        aim independently, so the placement is nudged rather than duplicated.
        """
        half_depth = stage_depth / 2
        step = -0.05 if z > 0 else 0.05
        key = (round(x, 2), round(y, 2), round(z, 2))
        for _ in range(400):
            if key not in occupied:
                break
            z = _clamp(z + step, -half_depth, half_depth)
            key = (round(x, 2), round(y, 2), round(z, 2))
        else:
            logger.warning(
                "No free placement near x=%.2f y=%.2f z=%.2f; fixtures will overlap",
                x, y, z,
            )
        occupied.add(key)
        return key
