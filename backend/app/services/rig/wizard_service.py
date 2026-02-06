"""
Quick Rig Wizard Service
========================

Provides venue presets and automatic fixture placement for the
guided rig creation wizard.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# Venue presets with suggested fixtures and stage dimensions
VENUE_PRESETS = {
    "small_club": {
        "name": "Small Club / Bar",
        "description": "Intimate venue, 50-200 capacity",
        "stage_width": 6.0,
        "stage_depth": 4.0,
        "stage_height": 3.5,
        "suggested_fixtures": [
            {"fixture_type": "led_par", "count": 6, "group_name": "Front Wash"},
            {"fixture_type": "moving_head", "count": 2, "group_name": "Moving Heads"},
            {"fixture_type": "led_bar", "count": 2, "group_name": "LED Bars"},
        ],
    },
    "medium_venue": {
        "name": "Medium Venue",
        "description": "Mid-size club or ballroom, 200-800 capacity",
        "stage_width": 10.0,
        "stage_depth": 8.0,
        "stage_height": 5.0,
        "suggested_fixtures": [
            {"fixture_type": "led_par", "count": 8, "group_name": "Front Wash"},
            {"fixture_type": "moving_head", "count": 4, "group_name": "Moving Heads"},
            {"fixture_type": "led_bar", "count": 4, "group_name": "LED Bars"},
            {"fixture_type": "wash", "count": 4, "group_name": "Washes"},
        ],
    },
    "church": {
        "name": "House of Worship",
        "description": "Church or worship space, warm lighting",
        "stage_width": 12.0,
        "stage_depth": 6.0,
        "stage_height": 6.0,
        "suggested_fixtures": [
            {"fixture_type": "led_par", "count": 8, "group_name": "Front Wash"},
            {"fixture_type": "wash", "count": 4, "group_name": "Stage Wash"},
            {"fixture_type": "spot", "count": 2, "group_name": "Key Light"},
        ],
    },
    "theater": {
        "name": "Theater",
        "description": "Traditional theater or concert hall",
        "stage_width": 14.0,
        "stage_depth": 10.0,
        "stage_height": 8.0,
        "suggested_fixtures": [
            {"fixture_type": "spot", "count": 6, "group_name": "Front Spots"},
            {"fixture_type": "wash", "count": 6, "group_name": "Stage Wash"},
            {"fixture_type": "moving_head", "count": 4, "group_name": "Moving Heads"},
            {"fixture_type": "led_bar", "count": 4, "group_name": "Cyc Lights"},
            {"fixture_type": "led_par", "count": 8, "group_name": "Side Wash"},
        ],
    },
    "festival_stage": {
        "name": "Festival Stage",
        "description": "Outdoor festival or large event stage",
        "stage_width": 18.0,
        "stage_depth": 12.0,
        "stage_height": 10.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 8, "group_name": "Moving Heads"},
            {"fixture_type": "wash", "count": 8, "group_name": "Washes"},
            {"fixture_type": "led_bar", "count": 8, "group_name": "LED Bars"},
            {"fixture_type": "strobe", "count": 4, "group_name": "Strobes"},
            {"fixture_type": "beam", "count": 4, "group_name": "Beams"},
            {"fixture_type": "led_par", "count": 12, "group_name": "Front Wash"},
        ],
    },
    "large_venue": {
        "name": "Large Venue / Arena",
        "description": "Concert arena or large indoor venue",
        "stage_width": 20.0,
        "stage_depth": 14.0,
        "stage_height": 12.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 12, "group_name": "Moving Heads"},
            {"fixture_type": "wash", "count": 10, "group_name": "Washes"},
            {"fixture_type": "led_bar", "count": 10, "group_name": "LED Bars"},
            {"fixture_type": "spot", "count": 6, "group_name": "Spots"},
            {"fixture_type": "beam", "count": 6, "group_name": "Beams"},
            {"fixture_type": "strobe", "count": 6, "group_name": "Strobes"},
            {"fixture_type": "led_par", "count": 16, "group_name": "Front Wash"},
        ],
    },
    "nightclub": {
        "name": "Nightclub",
        "description": "Dance club or DJ venue",
        "stage_width": 8.0,
        "stage_depth": 6.0,
        "stage_height": 4.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 4, "group_name": "Moving Heads"},
            {"fixture_type": "led_par", "count": 8, "group_name": "Wash"},
            {"fixture_type": "led_bar", "count": 4, "group_name": "LED Bars"},
            {"fixture_type": "strobe", "count": 2, "group_name": "Strobes"},
            {"fixture_type": "laser", "count": 2, "group_name": "Lasers"},
            {"fixture_type": "effect", "count": 2, "group_name": "Effects"},
        ],
    },
    "outdoor": {
        "name": "Outdoor Event",
        "description": "Outdoor concert or event space",
        "stage_width": 15.0,
        "stage_depth": 10.0,
        "stage_height": 8.0,
        "suggested_fixtures": [
            {"fixture_type": "moving_head", "count": 6, "group_name": "Moving Heads"},
            {"fixture_type": "wash", "count": 6, "group_name": "Washes"},
            {"fixture_type": "led_par", "count": 10, "group_name": "Front Wash"},
            {"fixture_type": "led_bar", "count": 6, "group_name": "LED Bars"},
            {"fixture_type": "beam", "count": 4, "group_name": "Beams"},
        ],
    },
}


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
    def compute_placement(
        stage_width: float,
        stage_depth: float,
        stage_height: float,
        fixtures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compute automatic fixture placement positions.

        Groups fixtures by group_name and places them along truss lines
        with symmetric spacing.

        Each fixture dict should have: fixture_id, count, group_name, mode_channel_count (optional).
        Returns list of placement dicts with position/addressing info.
        """
        placements = []
        dmx_address = 1
        universe = 0

        for group in fixtures:
            count = group.get("count", 1)
            group_name = group.get("group_name", "Default")
            fixture_id = group.get("fixture_id")
            mode_id = group.get("mode_id")
            channel_count = group.get("mode_channel_count", 16)

            # Determine placement strategy based on group name
            positions = WizardService._compute_group_positions(
                group_name, count, stage_width, stage_depth, stage_height
            )

            for i, pos in enumerate(positions):
                # Check universe boundary
                if dmx_address + channel_count - 1 > 512:
                    universe += 1
                    dmx_address = 1

                placements.append({
                    "fixture_id": fixture_id,
                    "mode_id": mode_id,
                    "name": f"{group_name} {i + 1}",
                    "group_name": group_name,
                    "universe": universe,
                    "dmx_address": dmx_address,
                    "position_x": pos["x"],
                    "position_y": pos["y"],
                    "position_z": pos["z"],
                    "rotation_y": pos.get("rotation_y", 0.0),
                })

                dmx_address += channel_count

        return placements

    @staticmethod
    def _compute_group_positions(
        group_name: str,
        count: int,
        stage_width: float,
        stage_depth: float,
        stage_height: float,
    ) -> List[Dict[str, float]]:
        """Compute positions for a group of fixtures.

        Places fixtures symmetrically based on common group naming conventions.
        """
        positions = []
        group_lower = group_name.lower()

        # Determine placement line (y-height and z-depth)
        if "front" in group_lower or "wash" in group_lower:
            y = stage_height - 0.5
            z = 0.0  # Front of stage
        elif "cyc" in group_lower or "back" in group_lower:
            y = stage_height - 1.0
            z = stage_depth - 0.5  # Back of stage (floor level bars)
        elif "side" in group_lower:
            y = stage_height - 1.0
            z = stage_depth * 0.4
        else:
            # Default: main truss position
            y = stage_height - 0.5
            z = stage_depth * 0.3

        # Symmetric spacing along width
        if count == 1:
            positions.append({"x": 0.0, "y": y, "z": z})
        else:
            usable_width = stage_width * 0.8
            spacing = usable_width / (count - 1) if count > 1 else 0
            start_x = -usable_width / 2

            for i in range(count):
                x = start_x + (i * spacing)
                positions.append({"x": round(x, 2), "y": y, "z": round(z, 2)})

        return positions
