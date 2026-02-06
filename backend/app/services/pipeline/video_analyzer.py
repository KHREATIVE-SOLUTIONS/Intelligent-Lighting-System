"""
Video Analysis Pipeline
=======================

Extracts lighting state from concert video footage for training data.
This is the computer vision side of the video-to-DMX pipeline.

Pipeline stages:
1. Frame extraction at 2-5 fps
2. Fixture detection (YOLO)
3. Color extraction per fixture region
4. Brightness/intensity estimation
5. Movement tracking across frames (optical flow)
6. Effect classification (strobe, chase, etc.)
7. Output: per-frame lighting state estimation
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)


class DetectedFixtureType(Enum):
    """Types of fixtures detectable in video."""
    MOVING_HEAD = "moving_head"
    PAR_CAN = "par_can"
    LED_BAR = "led_bar"
    STROBE = "strobe"
    LASER = "laser"
    SPOTLIGHT = "spotlight"
    WASH_LIGHT = "wash_light"
    EFFECT_LIGHT = "effect_light"
    UNKNOWN = "unknown"


class DetectedEffect(Enum):
    """Effects detectable from video analysis."""
    NONE = "none"
    STROBE_FLASH = "strobe_flash"
    COLOR_CHASE = "color_chase"
    BLACKOUT = "blackout"
    FULL_ON = "full_on"
    SLOW_FADE = "slow_fade"
    BEAM_MOVEMENT = "beam_movement"
    GOBO_PATTERN = "gobo_pattern"
    HAZE_BEAM = "haze_beam"


@dataclass
class BoundingBox:
    """Bounding box for a detection."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class FixtureDetection:
    """A single detected fixture in a video frame."""
    fixture_type: DetectedFixtureType = DetectedFixtureType.UNKNOWN
    bbox: BoundingBox = field(default_factory=lambda: BoundingBox(0, 0, 0, 0))
    confidence: float = 0.0
    track_id: Optional[int] = None    # Persistent ID across frames

    # Estimated state
    color_rgb: Tuple[float, float, float] = (1.0, 1.0, 1.0)  # Detected color (0-1)
    color_hsv: Tuple[float, float, float] = (0.0, 0.0, 1.0)  # HSV representation
    brightness: float = 0.5           # Estimated dimmer (0-1)
    is_active: bool = True            # Whether the fixture appears to be on

    # Beam tracking
    beam_angle: Optional[float] = None     # Estimated beam angle in degrees
    beam_direction: Optional[Tuple[float, float]] = None  # Normalized beam direction


@dataclass
class BeamState:
    """State of a tracked light beam."""
    origin: Tuple[float, float] = (0.0, 0.0)     # Beam origin point
    endpoint: Tuple[float, float] = (0.0, 0.0)   # Beam endpoint
    angle_pan: float = 0.0            # Estimated pan angle
    angle_tilt: float = 0.0           # Estimated tilt angle
    width: float = 0.0                # Beam width in pixels
    intensity: float = 0.0            # Beam brightness
    color_rgb: Tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass
class VideoFrame:
    """Complete analysis of a single video frame."""
    frame_number: int = 0
    timestamp: float = 0.0
    width: int = 0
    height: int = 0

    # Detected fixtures
    fixtures: List[FixtureDetection] = field(default_factory=list)

    # Beam tracking
    beams: List[BeamState] = field(default_factory=list)

    # Frame-level estimates
    overall_brightness: float = 0.0   # Average frame brightness
    dominant_colors: List[Tuple[float, float, float]] = field(default_factory=list)
    detected_effects: List[DetectedEffect] = field(default_factory=list)

    # Exposure estimation for normalization
    exposure_estimate: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for training data export."""
        return {
            "frame_number": self.frame_number,
            "timestamp": self.timestamp,
            "fixtures": [
                {
                    "type": f.fixture_type.value,
                    "bbox": [f.bbox.x1, f.bbox.y1, f.bbox.x2, f.bbox.y2],
                    "confidence": f.confidence,
                    "track_id": f.track_id,
                    "color_rgb": list(f.color_rgb),
                    "brightness": f.brightness,
                    "is_active": f.is_active,
                    "beam_angle": f.beam_angle,
                }
                for f in self.fixtures
            ],
            "beams": [
                {
                    "origin": list(b.origin),
                    "endpoint": list(b.endpoint),
                    "angle_pan": b.angle_pan,
                    "angle_tilt": b.angle_tilt,
                    "intensity": b.intensity,
                    "color_rgb": list(b.color_rgb),
                }
                for b in self.beams
            ],
            "overall_brightness": self.overall_brightness,
            "dominant_colors": [list(c) for c in self.dominant_colors],
            "detected_effects": [e.value for e in self.detected_effects],
        }


class VideoAnalyzerPipeline:
    """Orchestrates the video analysis pipeline.

    Processes video frames through detection, color extraction,
    movement tracking, and effect classification stages.
    """

    def __init__(self):
        self.yolo_model = None
        self.sam2_model = None
        self.tracker = None
        self.loaded = False

        # Tracking state
        self._prev_frame: Optional[np.ndarray] = None
        self._prev_detections: List[FixtureDetection] = []
        self._track_id_counter = 0
        self._frame_count = 0

    async def load_models(self, model_manager=None) -> bool:
        """Load computer vision models for video analysis.

        Args:
            model_manager: The ML ModelManager for accessing YOLO etc.
        """
        if model_manager and model_manager.has_model("yolo"):
            self.yolo_model = model_manager.models.get("yolo")
            self.loaded = True
            logger.info("Video analyzer loaded with YOLO from model manager")
            return True

        # Try loading YOLO directly
        try:
            from ultralytics import YOLO
            # Try common model paths
            for path in [
                "ml_models/yolo11/yolo11l_fixtures.pt",
                "ml_models/yolo11/yolo11l.pt",
                "ml_models/yolov9/model.pt",
            ]:
                p = Path(path)
                if p.exists():
                    self.yolo_model = YOLO(str(p))
                    self.loaded = True
                    logger.info("Video analyzer loaded YOLO from %s", p)
                    return True
        except ImportError:
            logger.warning("ultralytics not installed for video analysis")

        logger.info("Video analyzer running without YOLO (limited functionality)")
        return False

    async def analyze_frame(
        self,
        frame: np.ndarray,
        timestamp: float = 0.0,
        frame_number: int = 0,
    ) -> VideoFrame:
        """Analyze a single video frame.

        Args:
            frame: BGR image as numpy array (H, W, 3)
            timestamp: Frame timestamp in seconds
            frame_number: Sequential frame number

        Returns:
            VideoFrame with all detected lighting information
        """
        h, w = frame.shape[:2]
        result = VideoFrame(
            frame_number=frame_number,
            timestamp=timestamp,
            width=w,
            height=h,
        )

        # Stage 1: Fixture detection
        if self.yolo_model:
            result.fixtures = await self._detect_fixtures(frame)
        else:
            # Fallback: bright region detection
            result.fixtures = self._detect_bright_regions(frame)

        # Stage 2: Color extraction per fixture
        for fixture in result.fixtures:
            self._extract_fixture_color(frame, fixture)

        # Stage 3: Overall frame analysis
        result.overall_brightness = self._estimate_brightness(frame)
        result.dominant_colors = self._extract_dominant_colors(frame)
        result.exposure_estimate = self._estimate_exposure(frame)

        # Stage 4: Effect detection
        result.detected_effects = self._detect_effects(frame, result)

        # Stage 5: Movement tracking (needs previous frame)
        if self._prev_frame is not None:
            result.beams = self._track_beams(self._prev_frame, frame)
            self._update_tracking(result.fixtures)

        self._prev_frame = frame.copy()
        self._prev_detections = result.fixtures
        self._frame_count += 1

        return result

    async def _detect_fixtures(
        self, frame: np.ndarray
    ) -> List[FixtureDetection]:
        """Detect fixtures using YOLO."""
        detections = []
        try:
            results = self.yolo_model(frame, conf=0.3, verbose=False)
            for result in results:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    class_name = result.names.get(class_id, "unknown")
                    fixture_type = self._map_class_to_fixture_type(class_name)

                    coords = box.xyxy[0]
                    detections.append(FixtureDetection(
                        fixture_type=fixture_type,
                        bbox=BoundingBox(
                            x1=float(coords[0]),
                            y1=float(coords[1]),
                            x2=float(coords[2]),
                            y2=float(coords[3]),
                        ),
                        confidence=float(box.conf[0]),
                        track_id=self._assign_track_id(
                            float(coords[0]), float(coords[1]),
                            float(coords[2]), float(coords[3]),
                        ),
                    ))
        except Exception as e:
            logger.warning("YOLO detection error: %s", e)

        return detections

    def _detect_bright_regions(
        self, frame: np.ndarray
    ) -> List[FixtureDetection]:
        """Fallback fixture detection using brightness thresholding."""
        try:
            import cv2
        except ImportError:
            return []

        detections = []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 100:  # Skip tiny regions
                continue
            x, y, w, h = cv2.boundingRect(contour)
            detections.append(FixtureDetection(
                fixture_type=DetectedFixtureType.UNKNOWN,
                bbox=BoundingBox(x1=x, y1=y, x2=x + w, y2=y + h),
                confidence=0.5,
                is_active=True,
            ))

        return detections

    def _extract_fixture_color(
        self, frame: np.ndarray, fixture: FixtureDetection
    ):
        """Extract dominant color from a fixture's bounding box region."""
        try:
            import cv2
        except ImportError:
            return

        bbox = fixture.bbox
        h, w = frame.shape[:2]

        # Clamp to frame bounds
        x1 = max(0, int(bbox.x1))
        y1 = max(0, int(bbox.y1))
        x2 = min(w, int(bbox.x2))
        y2 = min(h, int(bbox.y2))

        if x2 <= x1 or y2 <= y1:
            return

        region = frame[y1:y2, x1:x2]
        if region.size == 0:
            return

        # Convert to HSV
        hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Filter low-saturation pixels (white/grey haze)
        mask = hsv_region[:, :, 1] > 30  # S > ~12% (30/255)
        if np.sum(mask) > 10:
            # Use high-saturation pixels for color
            h_vals = hsv_region[:, :, 0][mask]
            s_vals = hsv_region[:, :, 1][mask]
            v_vals = hsv_region[:, :, 2][mask]

            # Median for robustness
            fixture.color_hsv = (
                float(np.median(h_vals)) / 180.0 * 360.0,  # OpenCV H is 0-180
                float(np.median(s_vals)) / 255.0,
                float(np.median(v_vals)) / 255.0,
            )
        else:
            # White/neutral light
            v_vals = hsv_region[:, :, 2]
            fixture.color_hsv = (0.0, 0.0, float(np.median(v_vals)) / 255.0)

        # Convert HSV to RGB
        h_norm = fixture.color_hsv[0] / 360.0
        s_norm = fixture.color_hsv[1]
        v_norm = fixture.color_hsv[2]

        # Simple HSV->RGB
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h_norm, s_norm, v_norm)
        fixture.color_rgb = (r, g, b)

        # Brightness from V channel
        fixture.brightness = fixture.color_hsv[2]

    def _estimate_brightness(self, frame: np.ndarray) -> float:
        """Estimate overall frame brightness."""
        gray = np.mean(frame, axis=2) if len(frame.shape) == 3 else frame.astype(float)
        return float(np.percentile(gray, 95)) / 255.0

    def _extract_dominant_colors(
        self, frame: np.ndarray, k: int = 3
    ) -> List[Tuple[float, float, float]]:
        """Extract k dominant colors from the frame using k-means."""
        try:
            from sklearn.cluster import MiniBatchKMeans
        except ImportError:
            # Simplified fallback
            avg = np.mean(frame.reshape(-1, 3), axis=0) / 255.0
            return [(float(avg[2]), float(avg[1]), float(avg[0]))]  # BGR->RGB

        # Downsample for speed
        h, w = frame.shape[:2]
        small = frame[::4, ::4].reshape(-1, 3).astype(np.float32) / 255.0

        # Filter dark pixels
        brightness = np.mean(small, axis=1)
        bright_pixels = small[brightness > 0.1]

        if len(bright_pixels) < k:
            return [(0.0, 0.0, 0.0)]

        kmeans = MiniBatchKMeans(n_clusters=k, n_init=1, max_iter=10)
        kmeans.fit(bright_pixels)
        centers = kmeans.cluster_centers_

        # Convert BGR to RGB and sort by brightness
        colors = [(float(c[2]), float(c[1]), float(c[0])) for c in centers]
        colors.sort(key=lambda c: sum(c), reverse=True)
        return colors

    def _estimate_exposure(self, frame: np.ndarray) -> float:
        """Estimate camera exposure for normalization."""
        gray = np.mean(frame, axis=2) if len(frame.shape) == 3 else frame.astype(float)
        return max(0.01, float(np.mean(gray)) / 128.0)

    def _detect_effects(
        self, frame: np.ndarray, video_frame: VideoFrame
    ) -> List[DetectedEffect]:
        """Detect active lighting effects from frame analysis."""
        effects = []

        # Strobe detection: very high brightness delta from previous frame
        if self._prev_frame is not None:
            prev_brightness = np.mean(self._prev_frame)
            curr_brightness = np.mean(frame)
            brightness_delta = abs(curr_brightness - prev_brightness)

            if brightness_delta > 80:  # Significant flash
                effects.append(DetectedEffect.STROBE_FLASH)
            elif curr_brightness < 10:
                effects.append(DetectedEffect.BLACKOUT)
            elif curr_brightness > 230:
                effects.append(DetectedEffect.FULL_ON)

        # No effects detected
        if not effects:
            effects.append(DetectedEffect.NONE)

        return effects

    def _track_beams(
        self, prev_frame: np.ndarray, curr_frame: np.ndarray
    ) -> List[BeamState]:
        """Track light beams between frames using optical flow."""
        # This is a placeholder for the full beam tracking implementation
        # which would use Hough lines + optical flow
        return []

    def _assign_track_id(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> int:
        """Assign a persistent track ID based on spatial proximity."""
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # Match with previous detections
        best_dist = float("inf")
        best_id = None

        for prev in self._prev_detections:
            pcx, pcy = prev.bbox.center
            dist = (cx - pcx) ** 2 + (cy - pcy) ** 2
            if dist < best_dist and dist < 2500:  # Max 50px movement
                best_dist = dist
                best_id = prev.track_id

        if best_id is not None:
            return best_id

        self._track_id_counter += 1
        return self._track_id_counter

    def _update_tracking(self, detections: List[FixtureDetection]):
        """Update tracking state with new detections."""
        self._prev_detections = detections

    def _map_class_to_fixture_type(self, class_name: str) -> DetectedFixtureType:
        """Map YOLO class name to fixture type enum."""
        name = class_name.lower().replace(" ", "_")
        mapping = {
            "moving_head": DetectedFixtureType.MOVING_HEAD,
            "moving_head_active": DetectedFixtureType.MOVING_HEAD,
            "moving_head_idle": DetectedFixtureType.MOVING_HEAD,
            "par_can": DetectedFixtureType.PAR_CAN,
            "par_active": DetectedFixtureType.PAR_CAN,
            "led_bar": DetectedFixtureType.LED_BAR,
            "led_bar_active": DetectedFixtureType.LED_BAR,
            "strobe": DetectedFixtureType.STROBE,
            "strobe_flash": DetectedFixtureType.STROBE,
            "laser": DetectedFixtureType.LASER,
            "laser_beam": DetectedFixtureType.LASER,
            "spotlight": DetectedFixtureType.SPOTLIGHT,
            "wash_light": DetectedFixtureType.WASH_LIGHT,
            "wash_active": DetectedFixtureType.WASH_LIGHT,
            "beam_active": DetectedFixtureType.MOVING_HEAD,
            "effect_light": DetectedFixtureType.EFFECT_LIGHT,
        }
        return mapping.get(name, DetectedFixtureType.UNKNOWN)

    def get_info(self) -> Dict[str, Any]:
        """Get pipeline status."""
        return {
            "loaded": self.loaded,
            "has_yolo": self.yolo_model is not None,
            "frames_processed": self._frame_count,
            "active_tracks": self._track_id_counter,
        }
