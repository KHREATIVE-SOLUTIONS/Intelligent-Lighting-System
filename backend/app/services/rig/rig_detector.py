"""
Rig Detector Service
====================

Uses YOLOv9 to detect fixtures in rig photos and auto-generate layouts.

Detection depends on the optional ultralytics (AGPL-3.0) extra, which is not
bundled. This module never imports it; it goes through ModelManager, which raises
ImportError when the extra is absent so the API can answer 503.
"""

import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from app.services.ml.model_manager import ModelManager


@dataclass
class DetectedFixture:
    """Represents a fixture detected in an image."""
    fixture_type: str
    confidence: float
    bbox: Dict[str, float]  # x1, y1, x2, y2
    center: Dict[str, float]  # x, y
    normalized_position: Dict[str, float]  # x, y normalized to 0-1


class RigDetector:
    """Detects fixtures in rig images and generates layouts."""

    # Mapping from YOLO classes to fixture types
    FIXTURE_CLASS_MAP = {
        'moving_head': 'moving_head',
        'par_can': 'led_par',
        'led_bar': 'led_bar',
        'strobe': 'strobe',
        'laser': 'laser',
        'spotlight': 'spot',
        'wash_light': 'wash',
        'effect_light': 'effect',
        # COCO classes that might be fixtures
        'tv': 'led_bar',  # Could be LED panel
        'traffic light': 'led_par',
        'stop sign': 'effect',
    }

    def __init__(self, model_manager: ModelManager):
        """Initialize the rig detector.

        Args:
            model_manager: The ML model manager instance
        """
        self.model_manager = model_manager

    async def detect_fixtures_in_image(
        self,
        image: np.ndarray,
        confidence_threshold: float = 0.3
    ) -> List[DetectedFixture]:
        """Detect fixtures in a rig image.

        Args:
            image: Image as numpy array (H, W, C) in BGR format
            confidence_threshold: Minimum confidence for detections

        Returns:
            List of detected fixtures

        Raises:
            ImportError: If the optional YOLOv9 fixture-detection extra is unavailable.
        """
        # Get image dimensions
        height, width = image.shape[:2]

        # Run YOLOv9 detection
        results = await self.model_manager.detect_fixtures(
            image,
            confidence_threshold=confidence_threshold
        )

        detected = []
        for fixture_data in results.get('fixtures', []):
            # Map class name to fixture type
            class_name = fixture_data.get('class_name', 'unknown').lower()
            fixture_type = self.FIXTURE_CLASS_MAP.get(class_name, 'other')

            bbox = fixture_data['bbox']
            center = fixture_data['center']

            # Normalize position to 0-1 range
            normalized_pos = {
                'x': center['x'] / width,
                'y': center['y'] / height
            }

            detected.append(DetectedFixture(
                fixture_type=fixture_type,
                confidence=fixture_data['confidence'],
                bbox=bbox,
                center=center,
                normalized_position=normalized_pos
            ))

        return detected

    def create_layout_from_detections(
        self,
        detections: List[DetectedFixture],
        stage_width: float = 10.0,
        stage_depth: float = 8.0,
        stage_height: float = 6.0,
        auto_group: bool = True
    ) -> Dict[str, Any]:
        """Create a rig layout from detected fixtures.

        Args:
            detections: List of detected fixtures
            stage_width: Stage width in meters
            stage_depth: Stage depth in meters
            stage_height: Stage height in meters
            auto_group: Automatically group fixtures by position

        Returns:
            Layout configuration dictionary
        """
        fixtures = []
        dmx_address = 1

        # Sort detections by X position for consistent addressing
        sorted_detections = sorted(detections, key=lambda d: d.normalized_position['x'])

        # Group fixtures by type and position
        groups = self._auto_group_fixtures(sorted_detections) if auto_group else {}

        for i, detection in enumerate(sorted_detections):
            # Convert normalized position to stage coordinates
            pos_x = (detection.normalized_position['x'] - 0.5) * stage_width
            pos_y = (0.5 - detection.normalized_position['y']) * stage_height  # Inverted Y
            pos_z = 0  # Assume flat plane

            # Determine DMX channel count based on fixture type
            channel_count = self._get_channel_count(detection.fixture_type)

            # Find group name
            group_name = None
            for gname, members in groups.items():
                if i in members:
                    group_name = gname
                    break

            fixtures.append({
                'fixture_type': detection.fixture_type,
                'name': f"{detection.fixture_type.replace('_', ' ').title()} {i + 1}",
                'dmx_address': dmx_address,
                'universe': 0,
                'position': {
                    'x': round(pos_x, 2),
                    'y': round(pos_y, 2),
                    'z': round(pos_z, 2)
                },
                'confidence': detection.confidence,
                'group_name': group_name,
                'channel_count': channel_count
            })

            dmx_address += channel_count

        return {
            'fixtures': fixtures,
            'total_count': len(fixtures),
            'groups': list(groups.keys()),
            'total_dmx_channels': dmx_address - 1,
            'stage_dimensions': {
                'width': stage_width,
                'depth': stage_depth,
                'height': stage_height
            }
        }

    def _auto_group_fixtures(
        self,
        detections: List[DetectedFixture]
    ) -> Dict[str, List[int]]:
        """Automatically group fixtures by type and position.

        Args:
            detections: List of detected fixtures

        Returns:
            Dictionary mapping group names to fixture indices
        """
        groups: Dict[str, List[int]] = {}

        # Group by fixture type first
        by_type: Dict[str, List[Tuple[int, DetectedFixture]]] = {}
        for i, det in enumerate(detections):
            if det.fixture_type not in by_type:
                by_type[det.fixture_type] = []
            by_type[det.fixture_type].append((i, det))

        for fixture_type, fixtures in by_type.items():
            if len(fixtures) <= 1:
                continue

            # Separate into left/right based on X position
            left_fixtures = [(i, d) for i, d in fixtures if d.normalized_position['x'] < 0.5]
            right_fixtures = [(i, d) for i, d in fixtures if d.normalized_position['x'] >= 0.5]

            # Check if fixtures are arranged symmetrically
            if len(left_fixtures) > 0 and len(right_fixtures) > 0:
                type_name = fixture_type.replace('_', ' ').title()

                if len(left_fixtures) > 1:
                    groups[f"{type_name} Left"] = [i for i, _ in left_fixtures]
                else:
                    groups[f"{type_name} Left"] = [left_fixtures[0][0]]

                if len(right_fixtures) > 1:
                    groups[f"{type_name} Right"] = [i for i, _ in right_fixtures]
                else:
                    groups[f"{type_name} Right"] = [right_fixtures[0][0]]
            else:
                # All on one side or centered
                groups[f"{fixture_type.replace('_', ' ').title()} All"] = [i for i, _ in fixtures]

        return groups

    def _get_channel_count(self, fixture_type: str) -> int:
        """Get the default DMX channel count for a fixture type.

        Args:
            fixture_type: Type of fixture

        Returns:
            Number of DMX channels
        """
        channel_counts = {
            'moving_head': 16,  # Pan, Tilt, Dimmer, RGB, Gobo, etc.
            'led_par': 8,       # Dimmer, RGB, Strobe, Mode
            'led_bar': 12,      # Multiple segments, RGB, Dimmer
            'wash': 14,         # Pan, Tilt, Dimmer, RGB(W), Zoom
            'spot': 18,         # Pan, Tilt, Dimmer, RGB, Gobo, Focus, Prism
            'beam': 16,         # Similar to moving head
            'strobe': 4,        # Dimmer, Rate, Duration, Mode
            'laser': 8,         # Pattern, Color, Size, Speed, etc.
            'effect': 6,        # Varies widely
            'dimmer': 1,        # Single channel
            'other': 4,         # Default
        }
        return channel_counts.get(fixture_type, 4)


class DemoRigGenerator:
    """Generates demo rig configurations for testing."""

    @staticmethod
    def create_symmetric_rig(
        num_movers_per_side: int = 4,
        num_washes_per_side: int = 3,
        num_bars_per_side: int = 2,
        stage_width: float = 12.0,
        stage_depth: float = 10.0,
        stage_height: float = 8.0
    ) -> Dict[str, Any]:
        """Create a symmetric demo rig.

        Args:
            num_movers_per_side: Number of moving heads per side
            num_washes_per_side: Number of wash lights per side
            num_bars_per_side: Number of LED bars/tetra bars per side
            stage_width: Stage width in meters
            stage_depth: Stage depth in meters
            stage_height: Stage height in meters

        Returns:
            Complete rig configuration
        """
        fixtures = []
        dmx_address = 1

        half_width = stage_width / 2

        # Moving heads - positioned at back truss
        mover_spacing = (stage_depth * 0.8) / max(num_movers_per_side, 1)
        for side in ['left', 'right']:
            x_pos = -half_width * 0.9 if side == 'left' else half_width * 0.9

            for i in range(num_movers_per_side):
                z_pos = -stage_depth * 0.4 + i * mover_spacing
                fixtures.append({
                    'fixture_type': 'moving_head',
                    'name': f"Mover {side.title()} {i + 1}",
                    'dmx_address': dmx_address,
                    'universe': 0,
                    'channel_count': 16,
                    'position': {
                        'x': round(x_pos, 2),
                        'y': round(stage_height * 0.9, 2),
                        'z': round(z_pos, 2)
                    },
                    'group_name': f"Movers {side.title()}",
                    'tags': ['mover', side, 'back_truss']
                })
                dmx_address += 16

        # Wash lights - positioned on mid truss
        wash_spacing = (stage_depth * 0.6) / max(num_washes_per_side, 1)
        for side in ['left', 'right']:
            x_pos = -half_width * 0.7 if side == 'left' else half_width * 0.7

            for i in range(num_washes_per_side):
                z_pos = -stage_depth * 0.3 + i * wash_spacing
                fixtures.append({
                    'fixture_type': 'wash',
                    'name': f"Wash {side.title()} {i + 1}",
                    'dmx_address': dmx_address,
                    'universe': 0,
                    'channel_count': 14,
                    'position': {
                        'x': round(x_pos, 2),
                        'y': round(stage_height * 0.75, 2),
                        'z': round(z_pos, 2)
                    },
                    'group_name': f"Washes {side.title()}",
                    'tags': ['wash', side, 'mid_truss']
                })
                dmx_address += 14

        # LED Bars / Tetra Bars - vertical or horizontal mounting
        bar_spacing = (stage_height * 0.5) / max(num_bars_per_side, 1)
        for side in ['left', 'right']:
            x_pos = -half_width * 0.95 if side == 'left' else half_width * 0.95

            for i in range(num_bars_per_side):
                y_pos = stage_height * 0.3 + i * bar_spacing
                fixtures.append({
                    'fixture_type': 'led_bar',
                    'name': f"Tetra Bar {side.title()} {i + 1}",
                    'dmx_address': dmx_address,
                    'universe': 0,
                    'channel_count': 12,
                    'position': {
                        'x': round(x_pos, 2),
                        'y': round(y_pos, 2),
                        'z': 0
                    },
                    'rotation': {
                        'x': 0,
                        'y': 0,
                        'z': 90 if side == 'left' else -90  # Vertical mounting
                    },
                    'group_name': f"Tetra Bars {side.title()}",
                    'tags': ['led_bar', 'tetra', side, 'side_truss']
                })
                dmx_address += 12

        return {
            'name': 'Demo Symmetric Rig',
            'description': 'Symmetric rig with movers, washes, and tetra bars on each side',
            'venue': 'Demo Venue',
            'stage_width': stage_width,
            'stage_depth': stage_depth,
            'stage_height': stage_height,
            'fixtures': fixtures,
            'total_fixtures': len(fixtures),
            'total_dmx_channels': dmx_address - 1,
            'groups': [
                'Movers Left', 'Movers Right',
                'Washes Left', 'Washes Right',
                'Tetra Bars Left', 'Tetra Bars Right'
            ],
            'universes': [{'universe': 0, 'protocol': 'artnet', 'port': 6454}]
        }


class PatternGenerator:
    """Generates DMX patterns based on fixture layouts."""

    def __init__(self):
        """Initialize the pattern generator."""
        pass

    def generate_x_pattern(
        self,
        fixtures: List[Dict[str, Any]],
        intensity: int = 255,
        color: Dict[str, int] = None
    ) -> Dict[str, int]:
        """Generate an X pattern across fixtures.

        Lights fixtures that form an X shape across the stage.

        Args:
            fixtures: List of fixture configurations
            intensity: Master intensity (0-255)
            color: Optional RGB color dict

        Returns:
            Dictionary mapping "universe:channel" to values
        """
        color = color or {'r': 255, 'g': 255, 'b': 255}
        dmx_values = {}

        if not fixtures:
            return dmx_values

        # Find stage bounds
        positions = [f['position'] for f in fixtures]
        min_x = min(p['x'] for p in positions)
        max_x = max(p['x'] for p in positions)
        min_y = min(p['y'] for p in positions)
        max_y = max(p['y'] for p in positions)

        for fixture in fixtures:
            pos = fixture['position']

            # Normalize position to -1 to 1
            if max_x != min_x:
                norm_x = 2 * (pos['x'] - min_x) / (max_x - min_x) - 1
            else:
                norm_x = 0

            if max_y != min_y:
                norm_y = 2 * (pos['y'] - min_y) / (max_y - min_y) - 1
            else:
                norm_y = 0

            # X pattern: fixtures close to diagonals (y=x or y=-x)
            dist_to_diag1 = abs(norm_y - norm_x) / 1.414
            dist_to_diag2 = abs(norm_y + norm_x) / 1.414
            dist_to_x = min(dist_to_diag1, dist_to_diag2)

            # Calculate intensity based on distance to X
            if dist_to_x < 0.3:  # Threshold for "on the X"
                fixture_intensity = int(intensity * (1 - dist_to_x / 0.3))
            else:
                fixture_intensity = 0

            # Set DMX values for this fixture
            universe = fixture.get('universe', 0)
            address = fixture['dmx_address']
            fixture_type = fixture.get('fixture_type', 'other')

            values = self._create_fixture_values(
                fixture_type, fixture_intensity, color
            )

            for offset, value in enumerate(values):
                key = f"{universe}:{address + offset}"
                dmx_values[key] = value

        return dmx_values

    def generate_centered_pattern(
        self,
        fixtures: List[Dict[str, Any]],
        intensity: int = 255,
        color: Dict[str, int] = None,
        falloff: float = 0.5
    ) -> Dict[str, int]:
        """Generate a centered pattern - brighter in center.

        Args:
            fixtures: List of fixture configurations
            intensity: Master intensity (0-255)
            color: Optional RGB color dict
            falloff: How quickly intensity falls off from center

        Returns:
            Dictionary mapping "universe:channel" to values
        """
        color = color or {'r': 255, 'g': 255, 'b': 255}
        dmx_values = {}

        if not fixtures:
            return dmx_values

        # Find stage center
        positions = [f['position'] for f in fixtures]
        center_x = sum(p['x'] for p in positions) / len(positions)
        center_y = sum(p['y'] for p in positions) / len(positions)

        # Find max distance for normalization
        max_dist = max(
            ((p['x'] - center_x)**2 + (p['y'] - center_y)**2)**0.5
            for p in positions
        ) or 1

        for fixture in fixtures:
            pos = fixture['position']

            # Distance from center
            dist = ((pos['x'] - center_x)**2 + (pos['y'] - center_y)**2)**0.5
            norm_dist = dist / max_dist

            # Intensity falloff from center
            fixture_intensity = int(intensity * max(0, 1 - norm_dist * falloff * 2))

            # Set DMX values
            universe = fixture.get('universe', 0)
            address = fixture['dmx_address']
            fixture_type = fixture.get('fixture_type', 'other')

            values = self._create_fixture_values(
                fixture_type, fixture_intensity, color
            )

            for offset, value in enumerate(values):
                key = f"{universe}:{address + offset}"
                dmx_values[key] = value

        return dmx_values

    def generate_side_pattern(
        self,
        fixtures: List[Dict[str, Any]],
        side: str = 'left',
        intensity: int = 255,
        color: Dict[str, int] = None
    ) -> Dict[str, int]:
        """Generate a pattern for one side only.

        Args:
            fixtures: List of fixture configurations
            side: 'left' or 'right'
            intensity: Master intensity (0-255)
            color: Optional RGB color dict

        Returns:
            Dictionary mapping "universe:channel" to values
        """
        color = color or {'r': 255, 'g': 255, 'b': 255}
        dmx_values = {}

        if not fixtures:
            return dmx_values

        # Find center X
        positions = [f['position'] for f in fixtures]
        center_x = sum(p['x'] for p in positions) / len(positions)

        for fixture in fixtures:
            pos = fixture['position']

            # Check if fixture is on the specified side
            if side == 'left' and pos['x'] < center_x:
                fixture_intensity = intensity
            elif side == 'right' and pos['x'] >= center_x:
                fixture_intensity = intensity
            else:
                fixture_intensity = 0

            # Set DMX values
            universe = fixture.get('universe', 0)
            address = fixture['dmx_address']
            fixture_type = fixture.get('fixture_type', 'other')

            values = self._create_fixture_values(
                fixture_type, fixture_intensity, color
            )

            for offset, value in enumerate(values):
                key = f"{universe}:{address + offset}"
                dmx_values[key] = value

        return dmx_values

    def generate_alternating_pattern(
        self,
        fixtures: List[Dict[str, Any]],
        group_a_intensity: int = 255,
        group_b_intensity: int = 0,
        color_a: Dict[str, int] = None,
        color_b: Dict[str, int] = None
    ) -> Dict[str, int]:
        """Generate alternating pattern (odd/even fixtures).

        Args:
            fixtures: List of fixture configurations
            group_a_intensity: Intensity for odd fixtures
            group_b_intensity: Intensity for even fixtures
            color_a: Color for odd fixtures
            color_b: Color for even fixtures

        Returns:
            Dictionary mapping "universe:channel" to values
        """
        color_a = color_a or {'r': 255, 'g': 255, 'b': 255}
        color_b = color_b or {'r': 255, 'g': 255, 'b': 255}
        dmx_values = {}

        # Sort fixtures by X position for consistent alternation
        sorted_fixtures = sorted(fixtures, key=lambda f: f['position']['x'])

        for i, fixture in enumerate(sorted_fixtures):
            is_group_a = i % 2 == 0

            fixture_intensity = group_a_intensity if is_group_a else group_b_intensity
            color = color_a if is_group_a else color_b

            universe = fixture.get('universe', 0)
            address = fixture['dmx_address']
            fixture_type = fixture.get('fixture_type', 'other')

            values = self._create_fixture_values(
                fixture_type, fixture_intensity, color
            )

            for offset, value in enumerate(values):
                key = f"{universe}:{address + offset}"
                dmx_values[key] = value

        return dmx_values

    def generate_sweep_pattern(
        self,
        fixtures: List[Dict[str, Any]],
        position: float = 0.5,
        width: float = 0.2,
        direction: str = 'horizontal',
        intensity: int = 255,
        color: Dict[str, int] = None
    ) -> Dict[str, int]:
        """Generate a sweep/wipe pattern.

        Args:
            fixtures: List of fixture configurations
            position: Position of the sweep (0-1)
            width: Width of the lit area (0-1)
            direction: 'horizontal' or 'vertical'
            intensity: Master intensity
            color: Optional RGB color dict

        Returns:
            Dictionary mapping "universe:channel" to values
        """
        color = color or {'r': 255, 'g': 255, 'b': 255}
        dmx_values = {}

        if not fixtures:
            return dmx_values

        positions = [f['position'] for f in fixtures]

        if direction == 'horizontal':
            min_val = min(p['x'] for p in positions)
            max_val = max(p['x'] for p in positions)
        else:
            min_val = min(p['y'] for p in positions)
            max_val = max(p['y'] for p in positions)

        range_val = max_val - min_val if max_val != min_val else 1

        for fixture in fixtures:
            pos = fixture['position']

            if direction == 'horizontal':
                norm_pos = (pos['x'] - min_val) / range_val
            else:
                norm_pos = (pos['y'] - min_val) / range_val

            # Calculate distance from sweep position
            dist = abs(norm_pos - position)

            if dist < width / 2:
                # Smooth falloff
                falloff = 1 - (dist / (width / 2))
                fixture_intensity = int(intensity * falloff)
            else:
                fixture_intensity = 0

            universe = fixture.get('universe', 0)
            address = fixture['dmx_address']
            fixture_type = fixture.get('fixture_type', 'other')

            values = self._create_fixture_values(
                fixture_type, fixture_intensity, color
            )

            for offset, value in enumerate(values):
                key = f"{universe}:{address + offset}"
                dmx_values[key] = value

        return dmx_values

    def _create_fixture_values(
        self,
        fixture_type: str,
        intensity: int,
        color: Dict[str, int]
    ) -> List[int]:
        """Create DMX values for a fixture.

        Args:
            fixture_type: Type of fixture
            intensity: Dimmer intensity (0-255)
            color: RGB color dict

        Returns:
            List of DMX values for the fixture
        """
        # Generic channel mappings (adjust for specific fixtures)
        if fixture_type == 'moving_head':
            # Ch1: Pan, Ch2: Pan Fine, Ch3: Tilt, Ch4: Tilt Fine,
            # Ch5: Speed, Ch6: Dimmer, Ch7: Shutter, Ch8-10: RGB
            return [
                128, 0,   # Pan (center)
                128, 0,   # Tilt (center)
                0,        # Speed
                intensity,  # Dimmer
                255,      # Shutter open
                int(color['r'] * intensity / 255),  # Red
                int(color['g'] * intensity / 255),  # Green
                int(color['b'] * intensity / 255),  # Blue
                0, 0, 0, 0, 0, 0  # Gobo, prism, etc.
            ]
        elif fixture_type == 'wash':
            # Ch1: Pan, Ch2: Pan Fine, Ch3: Tilt, Ch4: Tilt Fine,
            # Ch5: Dimmer, Ch6-9: RGBW, Ch10: Zoom
            return [
                128, 0,   # Pan
                128, 0,   # Tilt
                intensity,  # Dimmer
                int(color['r'] * intensity / 255),
                int(color['g'] * intensity / 255),
                int(color['b'] * intensity / 255),
                0,        # White
                128,      # Zoom (mid)
                0, 0, 0, 0  # Extra
            ]
        elif fixture_type == 'led_bar':
            # Tetra bar: Ch1: Dimmer, Ch2-4: RGB, Ch5: Strobe, Ch6-12: Segments
            return [
                intensity,
                int(color['r'] * intensity / 255),
                int(color['g'] * intensity / 255),
                int(color['b'] * intensity / 255),
                0,        # Strobe off
                0, 0, 0, 0, 0, 0, 0  # Segment modes
            ]
        elif fixture_type == 'led_par':
            return [
                intensity,
                int(color['r'] * intensity / 255),
                int(color['g'] * intensity / 255),
                int(color['b'] * intensity / 255),
                0, 0, 0, 0  # Strobe, UV, etc.
            ]
        elif fixture_type == 'strobe':
            return [intensity, 0, 0, 0]  # Intensity, rate, etc.
        else:
            # Generic 4-channel
            return [
                intensity,
                int(color['r'] * intensity / 255),
                int(color['g'] * intensity / 255),
                int(color['b'] * intensity / 255)
            ]
