# Video-to-DMX Training Pipeline

## Technical Design Document

### Intelligent Lighting System -- Learning from the World's Best Lighting Designers

**Version:** 1.0
**Date:** 2026-02-06
**Status:** Design / Pre-Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Video Analysis Pipeline](#2-video-analysis-pipeline)
3. [Video-to-DMX Mapping](#3-video-to-dmx-mapping)
4. [Training Architecture](#4-training-architecture)
5. [Data Collection Strategy](#5-data-collection-strategy)
6. [Computer Vision Techniques](#6-computer-vision-techniques)
7. [From Concept to Implementation](#7-from-concept-to-implementation)
8. [Challenges and Mitigations](#8-challenges-and-mitigations)
9. [Integration with Existing Codebase](#9-integration-with-existing-codebase)
10. [Proof of Concept Plan](#10-proof-of-concept-plan)

---

## 1. Executive Summary

### The Core Idea

Professional lighting designers spend decades mastering their craft. Their work is captured in thousands of hours of concert footage available online. This pipeline extracts that expertise by watching videos of top lighting shows and converting what it sees into structured training data that maps audio features to lighting states (DMX values). The result is an AI that can operate lighting rigs in the style of the world's best LDs.

### Why This Is Transformative

| Approach | Training Data Volume | Quality | Cost |
|---|---|---|---|
| Manual operator recording (current `TrainingRecorder`) | Hours per session, requires skilled operator | Depends on operator skill | High (operator time) |
| Synthetic generation | Unlimited but artificial | Low realism | Low |
| **Video extraction (this pipeline)** | **Thousands of hours from YouTube alone** | **World-class LDs** | **Compute only** |

### Pipeline Overview

```
VIDEO INPUT                    EXTRACTION                     TRAINING
+-----------------+           +-------------------+          +-------------------+
| Concert footage | --------> | CV Analysis       | -------> | Audio-Lighting    |
| (YouTube/Vimeo) |           | - Fixture detect  |          | Paired Dataset    |
|                 |           | - Color extract   |          | (JSONL format     |
| + Audio track   |           | - Movement track  |          |  compatible with  |
|                 |           | - Effect classify |          |  TrainingRecorder)|
+-----------------+           | - Beam analysis   |          +-------------------+
                              +-------------------+                   |
                                                                      v
                              +-------------------+          +-------------------+
                              | Target rig config | -------> | Rig-Adapted Model |
                              | (18 fixtures,     |          | Audio -> DMX      |
                              |  fixture types,   |          | Real-time @ 40fps |
                              |  positions)       |          +-------------------+
                              +-------------------+
```

---

## 2. Video Analysis Pipeline

### 2.1 Fixture Detection in Video

The existing YOLOv9 model (`ml_models/yolov9/model.pt`) with custom classes (`moving_head`, `par_can`, `led_bar`, `strobe`, `laser`, `spotlight`, `wash_light`, `effect_light`) provides the foundation. However, it needs fine-tuning for in-situ detection -- identifying active fixtures in concert footage rather than product photos.

**Approach: Two-Stage Detection**

**Stage 1 -- Light Source Detection (pixel-level)**
- Use a pretrained segmentation model (Segment Anything Model 2 / SAM2 from Meta, released 2024) to segment bright regions in each frame.
- Filter segments by brightness threshold (V > 0.7 in HSV space) to isolate active light sources.
- This does not require labeled data and works out-of-the-box.
- GitHub: `https://github.com/facebookresearch/sam2`

**Stage 2 -- Fixture Classification (bounding-box level)**
- Fine-tune YOLOv9 on a labeled dataset of concert screenshots with fixture bounding boxes.
- The existing 8-class configuration in `ml_models/yolov9/config.yaml` is a strong starting point.
- Use the `ultralytics` library already imported in `model_manager.py`.

**Fine-tuning procedure:**
```python
from ultralytics import YOLO

# Load existing model
model = YOLO("ml_models/yolov9/model.pt")

# Fine-tune on concert fixture dataset
model.train(
    data="datasets/concert_fixtures/data.yaml",
    epochs=100,
    imgsz=1280,      # Higher resolution for distant fixtures
    batch=8,
    name="yolov9_concert_fixtures",
    augment=True,     # Flip, rotate, color jitter
    mixup=0.1,        # Mix training images
    mosaic=1.0,       # Mosaic augmentation
)
```

**Annotation strategy:**
- Use Roboflow or CVAT to label 2,000-5,000 frames from diverse concert footage.
- Classes: `moving_head_active`, `moving_head_idle`, `par_active`, `led_bar_active`, `wash_active`, `beam_active`, `strobe_flash`, `laser_beam`, `haze_cone`.
- Active vs. idle distinction is critical -- we only care about fixtures that are emitting light.

### 2.2 Beam Tracking

Light beams are the primary visual indicator of pan/tilt position and intensity. Tracking them across frames reveals movement patterns.

**Technique: Hough Line Detection + Optical Flow**

```
Frame N                          Frame N+1
+---------------------------+    +---------------------------+
|     \  /   |   \  /      |    |      \  / |  \  /        |
|      \/    |    \/       |    |       \/  |   \/         |
|      /\    |    /\       |    |       /\  |   /\         |
|     /  \   |   /  \      |    |      /  \ |  /  \        |
|    source  |  source     |    |     source | source       |
+---------------------------+    +---------------------------+

Beam angle delta = pan/tilt change
```

**Implementation:**

1. **Bright pixel extraction:** Threshold the frame to isolate bright regions (beam cores).
2. **Probabilistic Hough Transform:** Detect line segments in the thresholded image. Each line represents a beam.
3. **Beam-to-fixture association:** Match detected beams to detected fixtures using proximity (beam origin should be near a fixture bounding box).
4. **Angle measurement:** Calculate beam angle from the line segment. The angle relative to vertical gives a proxy for tilt; the angle relative to center-stage gives a proxy for pan.
5. **Temporal tracking:** Use optical flow (Lucas-Kanade or RAFT -- see Section 6) to track beam endpoints across frames, giving smooth movement trajectories.

**Key library:** OpenCV `cv2.HoughLinesP()` for line detection, `cv2.calcOpticalFlowPyrLK()` for tracking.

**Alternative: Deep beam segmentation.** Train a U-Net or DeepLabV3 model to segment beam regions at the pixel level. This handles fog/haze beams better than Hough lines. The Stanford LLFF dataset and synthetic beam renders can provide training data.

### 2.3 Color Extraction

For each detected fixture or beam region, extract the dominant color per frame.

**Pipeline:**

```
Detected fixture region (bounding box or segment mask)
    |
    v
Convert to HSV color space
    |
    v
Filter low-saturation pixels (S < 0.15) -- these are white/grey haze, not fixture color
    |
    v
K-Means clustering (K=3) on remaining HSV pixels
    |
    v
Select cluster with highest V (brightness) as primary fixture color
    |
    v
Apply camera white-balance correction (see Section 6.4)
    |
    v
Output: (H, S, V) -> map to (R, G, B) DMX values
```

**Color accuracy considerations:**
- Concert cameras typically shoot in 709 or LOG color spaces. The pipeline should detect and compensate for these.
- Auto-white-balance causes color shifts. A reference-based correction can use known white light sources in the frame.
- LED fixtures have narrowband spectral output that cameras render differently than the human eye. A color correction matrix (CCM) trained on known LED colors helps.

**Integration with existing `ColorMapper`:**
The extracted colors map directly to the `RGB` dataclass in `color_mapper.py` (r, g, b in 0-1 range). The `ColorPalette` classification can be derived by clustering extracted colors across a full show and matching to the nearest palette in `COLOR_PRESETS`.

### 2.4 Brightness/Intensity Estimation

**Approach: Relative luminance within fixture regions.**

```python
def estimate_dimmer(fixture_region_hsv):
    """Estimate fixture dimmer value from video region."""
    # V channel in HSV = perceived brightness
    v_values = fixture_region_hsv[:, :, 2]

    # Use 95th percentile to avoid hot-pixel artifacts
    peak_brightness = np.percentile(v_values, 95)

    # Normalize against frame-level exposure estimate
    # (see exposure normalization in Section 6.4)
    normalized = peak_brightness / frame_exposure_estimate

    # Clamp to 0-1
    dimmer = min(1.0, max(0.0, normalized))

    return dimmer  # Maps to 0-255 DMX dimmer channel
```

**Temporal smoothing:** Apply a low-pass filter (exponential moving average, alpha=0.3) to prevent jitter from camera noise, but with an override for strobe detection (rapid changes should not be smoothed).

### 2.5 Movement Tracking

**Goal:** Extract pan/tilt trajectories for moving heads across time.

**Method 1: Beam endpoint tracking (preferred for mid-air beams)**
- Track where each beam hits the stage floor or a surface.
- The beam landing point's x-position correlates with pan; y-position (depth) correlates with tilt.
- Use homography estimation if the stage floor plane can be detected.

**Method 2: Fixture body orientation (for close-up shots)**
- If the camera is close enough to see the fixture body, estimate its orientation using pose estimation.
- A lightweight model (MobileNetV3 fine-tuned on fixture orientations) can predict pan/tilt angles from fixture body crops.

**Method 3: Optical flow for relative movement**
- Dense optical flow (RAFT model: `https://github.com/princeton-vl/RAFT`) between consecutive frames within fixture bounding boxes.
- The mean flow vector gives direction and speed of movement.
- Integrate flow vectors over time to reconstruct pan/tilt trajectories.

**Movement pattern classification:**
After extracting trajectories, classify them into the patterns already defined in the codebase's `MovementType` enum:

| Detected Trajectory Pattern | MovementType Mapping |
|---|---|
| Horizontal oscillation | `HORIZONTAL_SWEEP` |
| Circular path | `TRUE_CIRCLE` |
| Figure-8 path | `FIGURE_8` |
| Sequential activation left-to-right | `PAN_CHASE` |
| Symmetric from center outward | `CENTER_OUT_WAVE` |
| Mirrored left/right | `MIRROR_SWEEP` |
| Random rapid changes | `BALLYHOO` |

Use a 1D CNN or LSTM on the trajectory time series (sequence of [pan_delta, tilt_delta] per fixture) to classify movement patterns. Train on synthetic trajectories generated from the existing `MovementEngine` as ground truth.

### 2.6 Strobe Detection

Strobe effects produce distinctive signatures in the video signal.

**Detection algorithm:**

```python
def detect_strobe(brightness_history, fps=30):
    """
    Detect strobe from brightness time series.

    Args:
        brightness_history: List of frame-average brightness values
        fps: Video frame rate

    Returns:
        List of (start_frame, end_frame, frequency_hz) tuples
    """
    # Compute frame-to-frame brightness change
    deltas = np.abs(np.diff(brightness_history))

    # Strobe signature: alternating high deltas (bright-dark-bright-dark)
    # Threshold: delta > 0.4 of max brightness
    threshold = 0.4 * np.max(brightness_history)
    strobe_frames = deltas > threshold

    # Find contiguous strobe regions
    regions = find_contiguous_regions(strobe_frames, min_length=3)

    strobes = []
    for start, end in regions:
        # Estimate strobe frequency from zero-crossings
        segment = deltas[start:end]
        zero_crossings = np.sum(np.diff(np.sign(segment - np.mean(segment))) != 0)
        frequency = (zero_crossings / 2) * fps / (end - start)
        strobes.append((start, end, frequency))

    return strobes
```

**Mapping to DMX:** The detected frequency maps to the `StrobeController` parameters. The `StrobeMode` enum values `BURST`, `BEAT_LOCKED`, and `CONTINUOUS` can be classified based on duration and regularity.

### 2.7 Effect Classification

Beyond individual fixture parameters, we want to classify the overall lighting "look" or effect being used at each moment.

**Taxonomy (aligned with existing `EffectsEngine` states):**

| Effect Category | Visual Indicators | Maps To |
|---|---|---|
| Static look | All fixtures steady, no movement | `LightingState.BREAKDOWN`, `StaticLook.*` |
| Beat sync | Brightness pulses on beat | `DimmerType.BEAT_SYNC` |
| Chase | Sequential fixture activation | `DimmerType.CHASE`, `MovementType.PAN_CHASE` |
| Rainbow/color wash | Slow color cycling | `ColorChase` with blend |
| Strobe burst | Rapid full-white flashes | `StrobeMode.BURST` |
| Build-up | Increasing intensity/speed | `LightingState.BUILDUP` |
| Drop | Sudden high-energy moment | `LightingState.PEAK` |
| Blackout | All fixtures off | `EffectsEngine.blackout()` |
| Ballyhoo | Rapid random movement | `MovementType.BALLYHOO` |

**Classification model:** A temporal CNN (TCN) or Transformer operating on a window of extracted features (per-frame fixture colors, intensities, positions) classifies the current effect. Training data comes from the video analysis combined with manual annotation of effect types.

**Paper reference:** "Temporal Convolutional Networks for Action Segmentation and Detection" (Lea et al., 2017) -- the same architecture used for action segmentation in video is directly applicable to lighting effect segmentation.

### 2.8 Stage Layout Reconstruction

Estimating the 3D arrangement of fixtures from 2D video enables rig abstraction.

**Approach: Multi-view structure from motion (SfM)**

When multiple camera angles are available (common in professional multicam recordings):
1. Detect fixtures in each camera view.
2. Match fixtures across views using appearance and position cues.
3. Triangulate 3D positions using camera geometry (estimated from scene structure).

**Single-view estimation:**
When only one camera angle is available:
1. Use perspective cues (truss lines, stage geometry) to estimate a ground plane and a truss plane.
2. Fixtures on the truss are assumed to be at a known height (~4m for typical concert rigs).
3. Use the vanishing point of the truss line to estimate x-position spread.
4. Output: relative fixture positions in a normalized coordinate system (not absolute meters, but proportional layout).

**Tool:** COLMAP (`https://colmap.github.io/`) for multi-view reconstruction, or monocular depth estimation (MiDaS / Depth Anything V2) for single-view depth cues.

**Output format:** A fixture layout compatible with the `Fixture` dataclass positions (x, y, z fields) used in `fixture_groups.py`.

---

## 3. Video-to-DMX Mapping

### 3.1 Color to RGB DMX Channels

The extracted HSV color from video must be mapped to the DMX RGB channels (0-255 per channel) as defined in the fixture channel maps.

**Mapping pipeline:**

```
Video HSV color
    |
    v
Camera color correction (CCM)
    |
    v
sRGB linearization (remove gamma)
    |
    v
LED spectral compensation
    |
    v
Gamut mapping to fixture color space
    |
    v
DMX RGB values (0-255)
```

**Camera Color Correction Matrix (CCM):**

Most concert footage is shot on cameras with known color science. A 3x3 color correction matrix transforms camera RGB to a standardized color space:

```python
# Approximate CCM for typical broadcast camera
CCM_BROADCAST = np.array([
    [1.12, -0.08, -0.04],
    [-0.06,  1.10, -0.04],
    [-0.02, -0.06,  1.08]
])

def camera_to_fixture_rgb(camera_rgb, ccm=CCM_BROADCAST):
    """Convert camera-captured RGB to fixture output RGB."""
    corrected = ccm @ camera_rgb
    return np.clip(corrected, 0, 1)
```

**LED spectral compensation:**
LED fixtures produce narrow-band RGB that cameras capture differently than broad-spectrum sources. A calibration step (one-time per fixture type) generates a lookup table mapping perceived camera colors to required DMX values. For the general case (unknown fixture type), a generic LED compensation curve works:

```python
# Generic LED to camera compensation
# Reds appear more saturated on camera, blues less saturated
LED_COMPENSATION = {
    'red':   lambda v: v * 0.92,   # Reduce red slightly
    'green': lambda v: v * 1.00,   # Green is fairly accurate
    'blue':  lambda v: v * 1.15,   # Boost blue to compensate
}
```

**Integration:** The corrected RGB values map directly to the `fixture.red`, `fixture.green`, `fixture.blue` attributes (0.0-1.0 float range) used throughout `effects_engine.py`, and to DMX channels via the `get_dmx_frame()` method in `fixture_groups.py` which converts `int(fixture.red * 255)`.

### 3.2 Brightness to Dimmer DMX

```python
def brightness_to_dimmer_dmx(perceived_brightness, exposure_compensation=1.0):
    """
    Convert perceived video brightness to DMX dimmer value.

    LED fixtures have roughly square-law dimming curves.
    Camera sensors have gamma curves (~2.2).
    We need to invert both to get the original DMX value.

    Args:
        perceived_brightness: 0.0-1.0 brightness from video
        exposure_compensation: Factor for camera exposure (>1 = overexposed)

    Returns:
        DMX value 0-255
    """
    # Remove camera gamma (approximate inverse gamma 2.2)
    linear = perceived_brightness ** 2.2

    # Compensate for camera exposure
    linear = linear / exposure_compensation

    # Apply inverse fixture dimming curve (square-law)
    # DMX -> light output is approximately quadratic for most fixtures
    dmx_normalized = math.sqrt(linear)

    # Scale to 0-255
    dmx_value = int(max(0, min(255, dmx_normalized * 255)))

    return dmx_value
```

### 3.3 Movement to Pan/Tilt DMX

The beam tracking from Section 2.5 gives us beam angles. Converting to DMX pan/tilt values requires knowing the fixture's pan/tilt range.

**From the existing `Fixture` model (`fixture.py`):**
- `pan_range`: default 540 degrees
- `tilt_range`: default 270 degrees

**From the existing `get_dmx_frame()` in `fixture_groups.py`:**
```python
'pan': int(((fixture.pan + 270) / 540) * 255)   # -270 to +270 -> 0-255
'tilt': int(((fixture.tilt + 135) / 270) * 255)  # -135 to +135 -> 0-255
```

**Video beam angle to DMX conversion:**

```python
def beam_angle_to_pan_tilt_dmx(
    beam_azimuth_deg,    # Horizontal angle from center (0 = straight ahead)
    beam_elevation_deg,  # Vertical angle from horizontal (0 = level, 90 = straight down)
    fixture_pan_range=540.0,
    fixture_tilt_range=270.0
):
    """
    Convert observed beam angles to DMX pan/tilt values.

    Note: This gives RELATIVE values. Absolute calibration requires
    knowing the fixture's mounting orientation and position.
    """
    # Normalize to fixture range
    # Assume beam azimuth maps linearly to pan
    pan_normalized = beam_azimuth_deg / (fixture_pan_range / 2)  # -1 to +1
    pan_dmx = int((pan_normalized + 1) / 2 * 255)  # 0-255

    # Assume beam elevation maps linearly to tilt
    tilt_normalized = beam_elevation_deg / (fixture_tilt_range / 2)
    tilt_dmx = int((tilt_normalized + 1) / 2 * 255)

    return pan_dmx, tilt_dmx
```

### 3.4 Temporal Alignment

Audio and visual analysis must be precisely synchronized.

**Strategy:**

1. **Extract audio from video:** Use `ffmpeg` to demux the audio track.
   ```bash
   ffmpeg -i concert_video.mp4 -vn -acodec pcm_s16le -ar 44100 audio.wav
   ```

2. **Frame-accurate timestamps:** Map video frame numbers to audio sample positions.
   ```python
   audio_sample_for_frame = int(frame_number / video_fps * audio_sample_rate)
   ```

3. **Audio feature extraction:** Run BeatNet (beat detection) and HuBERT (mood classification) on the extracted audio, producing the same `AudioFrame` format used by `TrainingRecorder`:
   ```python
   audio_frame = AudioFrame(
       timestamp=frame_number / video_fps,
       bpm=detected_bpm,
       energy=rms_energy,
       bass=bass_band_energy,
       mid=mid_band_energy,
       high=high_band_energy,
       valence=mood_valence,
       arousal=mood_arousal,
       spectral_flux=spectral_flux,
       is_beat=beat_detected,
       beat_position=beat_count % 4,
       spectrum=spectrum_bins
   )
   ```

4. **Lighting frame construction:** The video-extracted lighting state becomes a `LightingFrame`:
   ```python
   lighting_frame = LightingFrame(
       timestamp=frame_number / video_fps,
       fixtures=[
           {
               'id': f'fixture_{i}',
               'pan': extracted_pan,
               'tilt': extracted_tilt,
               'dimmer': extracted_dimmer,
               'r': extracted_r,
               'g': extracted_g,
               'b': extracted_b
           }
           for i, fixture_data in enumerate(detected_fixtures)
       ],
       dmx_frame=reconstructed_dmx_512
   )
   ```

5. **Pairing:** The existing `TrainingRecorder._recording_loop()` pairs audio and lighting frames within a 50ms window. Our video-extracted frames are inherently synchronized (same video timestamp), so every frame produces a valid `TrainingFrame` pair.

### 3.5 Rig Abstraction -- The Key Innovation

The most important design decision in this pipeline is how to represent lighting intent independent of the specific rig.

**Abstract Lighting Description (ALD) format:**

Rather than raw DMX values, we define an intermediate representation:

```python
@dataclass
class AbstractLightingState:
    """Rig-independent description of a lighting moment."""
    timestamp: float

    # Global attributes
    overall_intensity: float          # 0-1
    dominant_color: Tuple[float, float, float]  # HSV
    secondary_color: Tuple[float, float, float] # HSV
    color_spread: float               # 0=monochrome, 1=rainbow

    # Spatial distribution (normalized 0-1 coordinates)
    intensity_map: List[float]        # Per-zone intensities (9 zones: 3x3 grid)
    color_map: List[Tuple]            # Per-zone colors

    # Movement
    movement_type: str                # From MovementType enum
    movement_speed: float             # Beats per cycle
    movement_amplitude: float         # 0-1
    movement_phase_spread: float      # 0=unison, 1=full spread

    # Effects
    active_effects: List[str]         # ["strobe", "chase", "rainbow", etc.]
    effect_intensity: float           # 0-1

    # Temporal context
    energy_level: str                 # "low", "medium", "high", "extreme"
    structure_position: str           # From LightingState enum values

    # Grouping behavior
    group_mode: str                   # "all", "odd_even", "left_right", "individual"
    group_contrast: float             # 0=same, 1=opposite
```

**Why this works:**
- A video with 200 fixtures showing a left-right color split maps to `group_mode="left_right"`, `group_contrast=0.8`, `dominant_color=(0, 1, 1)`, `secondary_color=(240, 1, 1)`.
- Replaying on the existing 18-fixture rig: the system assigns left-side fixtures (from `FixtureGroupManager.groups["left"]`) the dominant color and right-side fixtures the secondary color, with appropriate contrast.
- The same ALD replayed on an 8-fixture rig just uses fewer fixtures per group.

### 3.6 Fixture Count Normalization

**The problem:** Videos may show 200+ fixtures. The target rig has 18 (or 8, or 4).

**Solution: Zone-based abstraction.**

Divide the visual stage into a normalized grid:

```
+--------+--------+--------+
|  UL    |  UC    |  UR    |   U = Upper (truss)
+--------+--------+--------+
|  ML    |  MC    |  MR    |   M = Middle
+--------+--------+--------+
|  FL    |  FC    |  FR    |   F = Floor/front
+--------+--------+--------+
```

1. **In the video:** Each detected fixture is assigned to a zone based on its position in the frame. Multiple fixtures in the same zone are averaged (dominant color, mean intensity, consensus movement).

2. **On the target rig:** Each physical fixture is assigned to a zone based on its `(x, y, z)` position from `fixture_groups.py`. The zone's abstract state is applied.

3. **Fixture count scaling:**
   - If the target rig has more fixtures per zone than the video: duplicate the zone state across fixtures with phase offsets.
   - If the target rig has fewer fixtures per zone: the zone state represents the aggregate intent.

```python
def map_video_zones_to_rig(video_zones, rig_fixtures):
    """
    Map 9-zone abstract lighting state to physical rig fixtures.

    Args:
        video_zones: Dict[zone_name, ZoneState]  (from video analysis)
        rig_fixtures: List[Fixture]  (from fixture_groups.py)

    Returns:
        Dict[fixture_id, FixtureState]
    """
    # Assign rig fixtures to zones based on position
    fixture_zones = {}
    for fixture in rig_fixtures:
        zone = position_to_zone(fixture.x, fixture.y, fixture.z)
        fixture_zones.setdefault(zone, []).append(fixture)

    # Apply zone states
    results = {}
    for zone_name, zone_state in video_zones.items():
        fixtures_in_zone = fixture_zones.get(zone_name, [])
        for i, fixture in enumerate(fixtures_in_zone):
            phase = i / max(1, len(fixtures_in_zone))
            results[fixture.id] = zone_state.apply_to_fixture(
                fixture, phase_offset=phase
            )

    return results
```

---

## 4. Training Architecture

### 4.1 Two-Stage Pipeline (Recommended Primary Architecture)

```
                          STAGE 1                              STAGE 2
                   Video -> Abstract LD               Audio + Context -> DMX

+----------+     +-------------------+     +---------+     +------------------+
| Video    | --> | Video Encoder     | --> | Abstract| --> | Audio-to-Lighting|
| Frames   |     | (ViT / ConvNeXt) |     | Lighting|     | Transformer      |
+----------+     +-------------------+     | Desc.   |     |                  |
                                           | (ALD)   |     | Input: audio feat|
                                           +---------+     |   + ALD context  |
                                                |          | Output: DMX frame|
                                                |          +------------------+
                                                |                |
                                            TRAINING             |
                                            DATA ONLY        INFERENCE
                                                             (real-time)
```

**Stage 1 runs offline** during data preparation. It processes video into Abstract Lighting Descriptions. This is computationally expensive but only runs once per video.

**Stage 2 runs in real-time** during inference. It takes audio features (from BeatNet + HuBERT, already in the system) and produces DMX output for the configured rig. It has learned from thousands of hours of Stage 1 output what lighting "should look like" for any given audio context.

### 4.2 Stage 1: Video Encoder

**Architecture: Vision Transformer (ViT-L/14) + Temporal Aggregation**

```python
class VideoLightingEncoder(nn.Module):
    """
    Encodes video frames into Abstract Lighting Descriptions.
    Runs offline during data preparation.
    """
    def __init__(self):
        super().__init__()

        # Pretrained vision backbone (frozen initially, fine-tuned later)
        self.vision_encoder = timm.create_model(
            'convnext_base.fb_in22k_ft_in1k',  # Strong general features
            pretrained=True,
            num_classes=0  # Remove classification head
        )

        # Temporal aggregation (processes 8-frame windows)
        self.temporal = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=1024, nhead=8, dim_feedforward=2048,
                dropout=0.1, batch_first=True
            ),
            num_layers=4
        )

        # Output heads for Abstract Lighting Description
        self.intensity_head = nn.Linear(1024, 9)     # 9-zone intensities
        self.color_head = nn.Linear(1024, 9 * 3)     # 9-zone HSV colors
        self.movement_head = nn.Linear(1024, len(MovementType))  # Classification
        self.effect_head = nn.Linear(1024, num_effect_classes)
        self.structure_head = nn.Linear(1024, len(LightingState))
```

**Why ConvNeXt over ViT for this task:** ConvNeXt preserves spatial locality better than ViT, which matters for detecting where on the stage fixtures are active. It also runs faster at inference, and our data volume (thousands of videos) justifies a large model.

**Alternative: Use CLIP embeddings.** OpenAI's CLIP (or the open-source OpenCLIP) can encode video frames into a shared embedding space with text. This enables zero-shot queries like "strobe effect" or "blue wash" as a bootstrapping strategy before labeled data is available.

### 4.3 Stage 2: Audio-to-Lighting Transformer

**Architecture: Autoregressive Transformer with audio + lighting context**

This is the core model that runs in real-time during shows:

```python
class AudioToLightingModel(nn.Module):
    """
    Real-time model: audio features -> DMX output.

    Input:
        - Audio features (same as AudioFrame in training_recorder.py)
        - Previous N lighting states (autoregressive context)
        - Rig configuration (fixture types, positions)

    Output:
        - Next lighting state (per-fixture DMX values)
    """
    def __init__(self,
                 audio_dim=64,
                 lighting_dim=128,
                 num_fixtures=18,
                 context_length=32):
        super().__init__()

        self.num_fixtures = num_fixtures

        # Audio feature encoder
        self.audio_encoder = nn.Sequential(
            nn.Linear(12, 64),   # 12 audio features from AudioFrame
            nn.GELU(),
            nn.Linear(64, audio_dim)
        )

        # Lighting state encoder (previous states)
        self.lighting_encoder = nn.Sequential(
            nn.Linear(num_fixtures * 7, 256),  # 7 params per fixture
            nn.GELU(),
            nn.Linear(256, lighting_dim)
        )

        # Rig configuration encoder (fixed per setup)
        self.rig_encoder = nn.Sequential(
            nn.Linear(num_fixtures * 6, 128),  # Position + type per fixture
            nn.GELU(),
            nn.Linear(128, 64)
        )

        # Main transformer
        d_model = audio_dim + lighting_dim + 64
        self.transformer = nn.TransformerDecoder(
            nn.TransformerDecoderLayer(
                d_model=d_model, nhead=8,
                dim_feedforward=512, dropout=0.1,
                batch_first=True
            ),
            num_layers=6
        )

        # Output: per-fixture DMX values
        self.output_head = nn.Sequential(
            nn.Linear(d_model, 256),
            nn.GELU(),
            nn.Linear(256, num_fixtures * 7),  # pan, tilt, dim, R, G, B, strobe
            nn.Sigmoid()  # Normalized 0-1 output
        )

    def forward(self, audio_features, prev_lighting_states, rig_config):
        # Encode inputs
        audio = self.audio_encoder(audio_features)
        lighting = self.lighting_encoder(prev_lighting_states)
        rig = self.rig_encoder(rig_config)

        # Combine and process
        combined = torch.cat([audio, lighting, rig], dim=-1)
        output = self.transformer(combined.unsqueeze(1), combined.unsqueeze(1))

        # Generate DMX values
        dmx = self.output_head(output.squeeze(1))
        return dmx.view(-1, self.num_fixtures, 7)
```

**Model size:** ~15M parameters. Small enough for real-time inference on consumer GPU or even CPU at 40fps (matching `DMX_FPS` in `config.py`).

### 4.4 Self-Supervised Pre-Training

Before fine-tuning on video-extracted data, pre-train the audio-to-lighting model using self-supervised objectives:

**Task 1: Next-frame prediction**
Given audio features and the last N lighting states (extracted from video), predict the next lighting state. The video-extracted ALD serves as ground truth.

**Task 2: Masked lighting prediction**
Randomly mask 15% of lighting frames in a sequence. Predict the masked frames from audio + surrounding context. This teaches the model temporal coherence (lighting does not randomly jump).

**Task 3: Audio-lighting matching**
Given an audio clip and a lighting sequence, predict whether they belong together (positive pair from the same video) or are mismatched (negative pair from different videos). This is contrastive learning applied to the audio-visual domain.

### 4.5 Contrastive Learning -- AudioVisual Correspondence

**Framework: InfoNCE / CLIP-style contrastive learning**

```python
class AudioLightingCLIP(nn.Module):
    """
    Learn a shared embedding space for audio and lighting.

    Audio clips that "match" a lighting look should have similar embeddings.
    This enables:
    - Finding lighting references from audio queries
    - Generating lighting from audio by nearest-neighbor in embedding space
    """
    def __init__(self):
        super().__init__()
        self.audio_encoder = AudioEncoder(output_dim=256)
        self.lighting_encoder = LightingEncoder(output_dim=256)
        self.temperature = nn.Parameter(torch.tensor(0.07))

    def forward(self, audio_batch, lighting_batch):
        # Encode both modalities
        audio_emb = F.normalize(self.audio_encoder(audio_batch), dim=-1)
        light_emb = F.normalize(self.lighting_encoder(lighting_batch), dim=-1)

        # Cosine similarity matrix
        logits = audio_emb @ light_emb.T / self.temperature

        # Symmetric cross-entropy loss (CLIP-style)
        labels = torch.arange(len(logits), device=logits.device)
        loss = (F.cross_entropy(logits, labels) +
                F.cross_entropy(logits.T, labels)) / 2

        return loss
```

**Why this matters:** The contrastive model learns abstract relationships like "heavy bass + high energy = intense warm colors with fast movement" without explicitly programming these rules. It discovers the implicit visual language of professional lighting design.

### 4.6 Rig-Agnostic Representation

The Abstract Lighting Description (Section 3.5) is the key to rig independence. During training, the model learns to produce ALDs. During inference, a rig-specific adapter converts ALDs to DMX:

```
                    LEARNED (from video)          CONFIGURED (per venue)

Audio Features  --> [Audio-to-ALD Model] --> ALD --> [Rig Adapter] --> DMX Frame
                                                          ^
                                                          |
                                                    Rig config:
                                                    - 18 fixtures
                                                    - Fixture types
                                                    - Positions
                                                    - Channel maps
```

**Rig Adapter** is NOT a neural network -- it is deterministic mapping code that uses the `FixtureGroupManager` to assign ALD zones to physical fixtures:

```python
class RigAdapter:
    """Converts Abstract Lighting Description to DMX for a specific rig."""

    def __init__(self, fixture_manager: FixtureGroupManager):
        self.fixtures = fixture_manager
        self._build_zone_mapping()

    def _build_zone_mapping(self):
        """Map physical fixtures to 9-zone grid."""
        self.zone_fixtures = {}
        for fixture in self.fixtures.fixtures.values():
            zone = self._position_to_zone(fixture.x, fixture.y, fixture.z)
            self.zone_fixtures.setdefault(zone, []).append(fixture)

    def apply_ald(self, ald: AbstractLightingState) -> List[int]:
        """Convert ALD to 512-channel DMX frame."""
        for zone_idx, zone_name in enumerate(ZONE_NAMES):
            zone_intensity = ald.intensity_map[zone_idx]
            zone_color = ald.color_map[zone_idx]

            for fixture in self.zone_fixtures.get(zone_name, []):
                fixture.dimmer = zone_intensity * ald.overall_intensity
                h, s, v = zone_color
                fixture.set_color_hsv(h, s, v)

                # Apply movement if fixture supports it
                if fixture.fixture_type in ["mover", "wash"]:
                    self._apply_movement(fixture, ald)

        return self.fixtures.get_dmx_frame(universe=0)
```

---

## 5. Data Collection Strategy

### 5.1 Source Material

**Primary sources:**
| Source | Volume | Quality | Access |
|---|---|---|---|
| YouTube concert recordings | 100,000+ hours | Variable (phone to broadcast) | `yt-dlp` (see legal notes) |
| Vimeo professional reels | 10,000+ hours | High (LD portfolios) | `yt-dlp` |
| LD showreel compilations | 1,000+ hours | Very high (curated highlights) | `yt-dlp` |
| TV broadcast concerts | 5,000+ hours | Broadcast quality | Various |
| Conference/church live streams | 50,000+ hours | Medium | YouTube |

**Target: 5,000 hours of diverse, high-quality footage for initial training.**

### 5.2 Legal Considerations

**Fair use analysis for ML training:**
- In the US, the Authors Guild v. Google (2015) and Andy Warhol Foundation v. Goldsmith (2023) cases frame the debate. Using copyrighted footage to train AI models is an evolving legal area.
- The EU AI Act (2024) requires disclosure of copyrighted training data.
- **Recommended approach:**
  1. Prioritize Creative Commons licensed content (CC-BY, CC-BY-SA).
  2. Use only the extracted features (not the video itself) in the training dataset -- this is transformative use.
  3. Do not redistribute original video content.
  4. Maintain a dataset card documenting all source material.
  5. Comply with `robots.txt` and Terms of Service.
  6. Consider licensing deals with concert video distributors (e.g., Qello Concerts, Stingray).

**Safest path:** Partner with lighting designers who consent to their show recordings being used for ML training. Many LDs already publish showreels for promotional purposes.

### 5.3 Genre Diversity

**Target distribution:**

```
Genre              Target Hours    Lighting Style
--------------------------------------------------
EDM/Electronic     1,500           Fast, colorful, strobe-heavy
Rock/Metal           800           Red/amber, aggressive, beat-reactive
Pop                  700           Bright, varied, production-heavy
Hip-Hop/R&B          500           Purple/gold, bold looks
Theater/Musical      400           Subtle, narrative-driven
Church/Worship       400           Warm, atmospheric, slow transitions
Jazz/Blues           200           Minimal, warm, spotlight-focused
Corporate/Events     200           Professional, conservative
DJ Sets              300           EDM-style, single-operator
```

This diversity ensures the model can handle any genre, not just EDM.

### 5.4 Audio Extraction and Synchronization

```python
import subprocess

def extract_audio_from_video(video_path, output_path, sample_rate=44100):
    """Extract audio track from video file using ffmpeg."""
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn',                     # No video
        '-acodec', 'pcm_s16le',   # PCM format for BeatNet compatibility
        '-ar', str(sample_rate),   # Match AUDIO_SAMPLE_RATE from config.py
        '-ac', '2',                # Stereo
        '-y',                      # Overwrite
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path

def extract_frames_at_rate(video_path, output_dir, fps=30):
    """Extract video frames at specified rate."""
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f'fps={fps}',
        '-q:v', '2',              # High quality JPEG
        f'{output_dir}/frame_%06d.jpg'
    ]
    subprocess.run(cmd, check=True, capture_output=True)
```

### 5.5 Multi-Angle Footage

Professional concert recordings often include multiple camera angles. These are extremely valuable:

1. **Wide shots** reveal the full rig layout and overall lighting state.
2. **Close-ups** show individual fixture details (color, gobo, beam quality).
3. **Audience shots** capture the lighting from a different perspective, enabling 3D estimation.

**Strategy:** Prioritize multicam recordings. Use the wide shot as the primary analysis source and close-ups for validation/refinement.

### 5.6 Annotation Pipeline

**Semi-automated, three-tier approach:**

**Tier 1 -- Fully Automated (no human input):**
- Light source detection (SAM2)
- Color extraction (K-Means on HSV)
- Brightness estimation
- Strobe detection
- Audio feature extraction (BeatNet + HuBERT)
- Beat alignment

**Tier 2 -- Human-Assisted (spot-check corrections):**
- Fixture type classification (auto-proposed, human-verified on 10% of frames)
- Movement pattern classification (auto-proposed, human-verified)
- Effect type classification

**Tier 3 -- Fully Manual (expert annotation):**
- Stage layout estimation (verify 3D reconstruction)
- Song structure labels (intro/build/drop/breakdown for a subset)
- Quality rating for extracted data

**Tooling:** Use Label Studio (`https://labelstud.io/`) for human annotation tasks, connected to the auto-extraction pipeline for pre-labeling.

### 5.7 Data Quality Filtering

Not all concert footage is useful. Automated quality filters:

```python
class VideoQualityFilter:
    """Filter out low-quality footage before processing."""

    @staticmethod
    def filter(video_path):
        """
        Returns quality score 0-1 and boolean accept/reject.
        Minimum score for acceptance: 0.5
        """
        scores = {}

        # Resolution check (minimum 720p)
        width, height = get_video_resolution(video_path)
        scores['resolution'] = min(1.0, height / 1080)

        # Stability check (audience phone = shaky)
        stability = estimate_camera_stability(video_path)
        scores['stability'] = stability

        # Stage visibility (frame must show stage, not just audience)
        stage_visible = detect_stage_presence(video_path)
        scores['stage_visible'] = stage_visible

        # Lighting visibility (must actually show active lights)
        light_fraction = estimate_bright_pixel_fraction(video_path)
        scores['lighting'] = min(1.0, light_fraction / 0.1)

        # Audio quality (must have music, not just crowd noise)
        audio_quality = estimate_audio_quality(video_path)
        scores['audio'] = audio_quality

        overall = sum(scores.values()) / len(scores)
        return overall, overall >= 0.5, scores
```

**Rejections:**
- Audience phone recordings with excessive shake (stability < 0.3)
- Videos where the stage is rarely visible (concert vlogs, backstage content)
- Videos with no discernible music audio (silent timelapses, photo slideshows)
- Resolution below 480p (insufficient for color extraction)

---

## 6. Computer Vision Techniques

### 6.1 Light Source Segmentation

**Primary: SAM2 (Segment Anything Model 2) with brightness prompting**

SAM2 can segment arbitrary objects given point or box prompts. For light source segmentation:

```python
from sam2.sam2_image_predictor import SAM2ImagePredictor

def segment_light_sources(frame, brightness_threshold=0.7):
    """Segment active light sources in a concert frame."""
    # Convert to HSV and find bright regions
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    bright_mask = hsv[:, :, 2] > (brightness_threshold * 255)

    # Find connected components as prompt points
    contours, _ = cv2.findContours(
        bright_mask.astype(np.uint8),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    # Use centroids as SAM2 point prompts
    predictor = SAM2ImagePredictor.from_pretrained("facebook/sam2-hiera-large")
    predictor.set_image(frame)

    segments = []
    for contour in contours:
        M = cv2.moments(contour)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            masks, scores, _ = predictor.predict(
                point_coords=np.array([[cx, cy]]),
                point_labels=np.array([1])
            )

            best_mask = masks[np.argmax(scores)]
            segments.append({
                'mask': best_mask,
                'center': (cx, cy),
                'confidence': float(np.max(scores))
            })

    return segments
```

**Alternative: Custom U-Net for beam segmentation**

For high-throughput processing (thousands of videos), a smaller custom model is more practical:

- Architecture: U-Net with EfficientNet-B3 encoder
- Training data: 5,000 manually annotated frames with beam masks
- Output: 3-class segmentation (background, beam_core, beam_haze)
- Inference: ~15ms per frame on GPU (vs. ~200ms for SAM2)

### 6.2 Haze/Fog Estimation

Haze density directly affects beam visibility and perceived intensity. Dense haze makes beams appear wider and brighter; no haze makes only the fixture lens and beam target visible.

**Estimation approach:**

```python
def estimate_haze_density(frame, light_segments):
    """
    Estimate haze density from beam appearance.

    Returns: 0.0 (no haze) to 1.0 (dense fog)
    """
    if not light_segments:
        return 0.0

    # Measure the "softness" of beam edges
    # Dense haze = soft, diffused edges
    # No haze = hard edges (just the light source point)

    edge_softness_scores = []
    for segment in light_segments:
        mask = segment['mask']
        # Compute gradient magnitude at mask boundary
        edges = cv2.Canny(mask.astype(np.uint8) * 255, 50, 150)

        # Get pixel intensities at and near the boundary
        dilated = cv2.dilate(edges, np.ones((5,5)), iterations=2)
        boundary_region = dilated.astype(bool)

        if boundary_region.sum() > 0:
            boundary_values = frame[boundary_region].mean()
            interior_values = frame[mask.astype(bool)].mean()

            # Soft edges -> boundary values close to interior values
            softness = boundary_values / max(1, interior_values)
            edge_softness_scores.append(softness)

    if edge_softness_scores:
        return float(np.mean(edge_softness_scores))
    return 0.0
```

**Use in brightness estimation:** When haze is dense, perceived brightness from the beam overestimates the actual fixture output. Apply a haze compensation factor:

```python
adjusted_brightness = raw_brightness / (1.0 + haze_density * 0.5)
```

### 6.3 Camera Motion Compensation

Concert footage features camera movement (pans, tilts, zooms, cuts). This must be separated from fixture movement.

**Approach: Global motion estimation + subtraction**

```python
def compensate_camera_motion(prev_frame, curr_frame, fixture_bboxes):
    """
    Estimate global camera motion and subtract it from fixture tracking.

    Returns: camera_transform (affine matrix), stabilized fixture positions
    """
    # Convert to grayscale
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

    # Mask out bright light regions (not reliable for camera motion estimation)
    mask = np.ones_like(prev_gray, dtype=np.uint8) * 255
    for bbox in fixture_bboxes:
        x1, y1, x2, y2 = bbox
        mask[y1:y2, x1:x2] = 0

    # Find feature points in non-light regions (stage structure, audience)
    features = cv2.goodFeaturesToTrack(
        prev_gray, maxCorners=200, qualityLevel=0.01,
        minDistance=30, mask=mask
    )

    if features is None or len(features) < 10:
        return np.eye(3), fixture_bboxes  # Cannot estimate, assume no motion

    # Track features with optical flow
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(
        prev_gray, curr_gray, features, None
    )

    # Estimate affine transform from tracked points
    good_prev = features[status.flatten() == 1]
    good_curr = tracked[status.flatten() == 1]

    transform, inliers = cv2.estimateAffinePartial2D(
        good_prev, good_curr, method=cv2.RANSAC
    )

    if transform is not None:
        # Apply inverse transform to fixture positions to stabilize
        inv_transform = cv2.invertAffineTransform(transform)
        stabilized_bboxes = apply_transform_to_bboxes(fixture_bboxes, inv_transform)

        full_transform = np.vstack([transform, [0, 0, 1]])
        return full_transform, stabilized_bboxes

    return np.eye(3), fixture_bboxes
```

**Cut detection:** Rapid scene changes (cuts between camera angles) are detected by computing the histogram difference between consecutive frames. When the difference exceeds a threshold, reset all tracking and re-detect fixtures:

```python
def detect_scene_cut(prev_frame, curr_frame, threshold=0.5):
    """Detect hard cuts between camera angles."""
    prev_hist = cv2.calcHist([prev_frame], [0, 1, 2], None, [8, 8, 8],
                              [0, 256, 0, 256, 0, 256])
    curr_hist = cv2.calcHist([curr_frame], [0, 1, 2], None, [8, 8, 8],
                              [0, 256, 0, 256, 0, 256])
    correlation = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
    return correlation < threshold  # Low correlation = scene cut
```

### 6.4 Exposure Normalization

Concert footage features dramatic exposure changes -- cameras auto-expose differently for bright strobe moments vs. dark ambient scenes.

**Method: Reference-based normalization**

1. Identify stable reference regions in the frame (e.g., LED screens showing static content, lit signage, the stage floor under consistent wash light).
2. Track the brightness of these reference regions across frames.
3. Compute an exposure correction factor per frame.

```python
class ExposureNormalizer:
    """Normalize brightness across frames with varying camera exposure."""

    def __init__(self):
        self.reference_brightness = None
        self.reference_regions = []

    def calibrate(self, first_frames, num_frames=30):
        """Find stable reference regions from initial frames."""
        # Compute per-pixel brightness variance across frames
        brightness_stack = np.array([
            cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(float)
            for f in first_frames[:num_frames]
        ])
        variance = brightness_stack.var(axis=0)

        # Regions with LOW variance are stable references
        stable_mask = variance < np.percentile(variance, 10)

        # Find connected regions
        contours, _ = cv2.findContours(
            stable_mask.astype(np.uint8),
            cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Keep large stable regions
        self.reference_regions = [
            cv2.boundingRect(c) for c in contours
            if cv2.contourArea(c) > 500
        ]

        # Set reference brightness
        if self.reference_regions:
            ref_values = []
            for frame in first_frames[:num_frames]:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                for (x, y, w, h) in self.reference_regions:
                    ref_values.append(gray[y:y+h, x:x+w].mean())
            self.reference_brightness = np.mean(ref_values)

    def get_exposure_factor(self, frame):
        """Get exposure correction factor for a frame."""
        if not self.reference_regions or self.reference_brightness is None:
            return 1.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        current_ref = np.mean([
            gray[y:y+h, x:x+w].mean()
            for (x, y, w, h) in self.reference_regions
        ])

        if current_ref > 0:
            return self.reference_brightness / current_ref
        return 1.0
```

**Fallback when no stable references exist:** Use the median brightness of the bottom 25% of pixels (typically the audience/floor area) as a proxy for ambient exposure level.

### 6.5 Multi-Fixture Tracking

Maintaining fixture identity across frames is essential for tracking individual fixture parameters.

**Approach: DeepSORT tracking with fixture-specific features**

```python
from deep_sort_realtime.deepsort_tracker import DeepSort

class FixtureTracker:
    """Track individual fixtures across video frames."""

    def __init__(self):
        self.tracker = DeepSort(
            max_age=30,              # Keep lost tracks for 30 frames
            n_init=3,                # Require 3 detections to confirm
            max_iou_distance=0.7,
            max_cosine_distance=0.3,
        )
        self.fixture_histories = {}  # track_id -> list of states

    def update(self, frame, detections):
        """
        Update tracking with new detections.

        Args:
            frame: Current video frame (for appearance features)
            detections: List of detection dicts with bbox and confidence

        Returns:
            Dict[track_id, FixtureState]
        """
        # Format for DeepSORT: ([x1,y1,w,h], confidence, class)
        formatted = []
        for det in detections:
            bbox = det['bbox']
            x1, y1, x2, y2 = bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2']
            formatted.append(
                ([x1, y1, x2-x1, y2-y1], det['confidence'], det['class_name'])
            )

        # Update tracker
        tracks = self.tracker.update_tracks(formatted, frame=frame)

        results = {}
        for track in tracks:
            if not track.is_confirmed():
                continue

            track_id = track.track_id
            bbox = track.to_ltrb()

            # Extract fixture state from this region
            x1, y1, x2, y2 = map(int, bbox)
            region = frame[y1:y2, x1:x2]

            state = self._extract_fixture_state(region, bbox)
            results[track_id] = state

            # Store history
            self.fixture_histories.setdefault(track_id, []).append(state)

        return results
```

**Occlusion handling:** When fixtures overlap or beams cross, DeepSORT's appearance model helps maintain identity. Additional heuristics:
- Fixtures on a truss have fixed relative positions -- if fixture A is always left of fixture B, this constraint prevents ID swaps.
- Color consistency: a fixture that was blue 1 second ago is unlikely to suddenly become a different fixture (though its color may change, the transition should be smooth).

### 6.6 Inverse Rendering

The most sophisticated approach: treat the video frame as a rendered scene and work backward to estimate the light parameters that produced it.

**Differentiable rendering approach:**

```
Ground truth frame (from video)
         |
         v
    Compare (MSE + perceptual loss)
         ^
         |
Rendered frame (from estimated parameters)
         ^
         |
    Differentiable renderer
         ^
         |
    Light parameters (optimized via gradient descent)
    - Fixture positions, colors, intensities, beam angles
```

**Tools:**
- **Mitsuba 3** (`https://github.com/mitsuba-renderer/mitsuba3`) -- differentiable renderer, supports optimization of light parameters.
- **PyTorch3D** (`https://pytorch3d.org/`) -- differentiable rendering in PyTorch, integrates with ML training.
- **nvdiffrec** (`https://github.com/NVlabs/nvdiffrec`) -- NVIDIA's differentiable inverse rendering.

**Practical concern:** Full inverse rendering is computationally expensive (minutes per frame). It is best used on a small subset of keyframes to calibrate and validate the faster heuristic methods described in Sections 2.1-2.5.

**Paper reference:** "Neural Inverse Rendering for General Reflectance Photometric Stereo" (Kaya et al., ICML 2022) -- demonstrates recovering light properties from images using differentiable rendering.

---

## 7. From Concept to Implementation

### 7.1 Architecture Diagram

```
+============================================================================+
|                        VIDEO-TO-DMX TRAINING PIPELINE                       |
+============================================================================+

DATA COLLECTION LAYER
+--------------------+    +------------------+    +--------------------+
| Video Downloader   |    | Audio Extractor  |    | Quality Filter     |
| (yt-dlp)           |    | (ffmpeg)         |    | (resolution,       |
|                    |    |                  |    |  stability, etc.)  |
+--------+-----------+    +--------+---------+    +----------+---------+
         |                         |                         |
         v                         v                         v
+============================================================================+
| VIDEO PROCESSING LAYER                                                      |
|                                                                             |
|  +------------------+  +------------------+  +-------------------+          |
|  | Frame Extractor  |  | Audio Analyzer   |  | Scene Cut         |          |
|  | (ffmpeg @ 30fps) |  | (BeatNet+HuBERT) |  | Detector          |          |
|  +--------+---------+  +--------+---------+  +---------+---------+          |
|           |                      |                      |                   |
|           v                      v                      v                   |
|  +------------------+  +------------------+  +-------------------+          |
|  | Fixture Detector |  | Beat/Mood        |  | Camera Motion     |          |
|  | (YOLOv9 finetuned|  | Extractor        |  | Compensator       |          |
|  |  + SAM2 segments)|  | (AudioFrame fmt) |  | (optical flow)    |          |
|  +--------+---------+  +--------+---------+  +---------+---------+          |
|           |                      |                      |                   |
|           v                      |                      |                   |
|  +------------------+            |                      |                   |
|  | Fixture Tracker  |            |                      |                   |
|  | (DeepSORT)       |            |                      |                   |
|  +--------+---------+            |                      |                   |
|           |                      |                      |                   |
|           v                      |                      |                   |
+============================================================================+
| FEATURE EXTRACTION LAYER                                                    |
|                                                                             |
|  +------------------+  +------------------+  +-------------------+          |
|  | Color Extractor  |  | Brightness Est.  |  | Movement Tracker  |          |
|  | (K-Means HSV)    |  | (exposure-norm)  |  | (beam angles,     |          |
|  +--------+---------+  +--------+---------+  |  optical flow)    |          |
|           |                      |           +----------+---------+          |
|           v                      v                      v                   |
|  +------------------+  +------------------+  +-------------------+          |
|  | Strobe Detector  |  | Effect           |  | Layout            |          |
|  | (brightness      |  | Classifier       |  | Estimator         |          |
|  |  delta analysis) |  | (TCN model)      |  | (depth + SfM)     |          |
|  +--------+---------+  +--------+---------+  +---------+---------+          |
|           |                      |                      |                   |
+===========|======================|======================|===================+
            |                      |                      |
            v                      v                      v
+============================================================================+
| ABSTRACTION LAYER                                                           |
|                                                                             |
|  +---------------------------------------------------------------------+   |
|  | Abstract Lighting Description (ALD) Generator                        |   |
|  |                                                                      |   |
|  | Input:  per-fixture (color, intensity, position, movement)           |   |
|  |         + audio features + scene structure                           |   |
|  |                                                                      |   |
|  | Output: AbstractLightingState per frame                              |   |
|  |         - 9-zone intensity/color maps                                |   |
|  |         - movement type + params                                     |   |
|  |         - effect classification                                      |   |
|  |         - energy/structure labels                                    |   |
|  +---------------------------------------------------------------------+   |
|                                     |                                       |
+=====================================|=======================================+
                                      |
                                      v
+============================================================================+
| TRAINING DATA LAYER                                                         |
|                                                                             |
|  +---------------------------------------------------------------------+   |
|  | TrainingFrame JSONL Writer                                           |   |
|  | (Compatible with training_recorder.py format)                        |   |
|  |                                                                      |   |
|  | {                                                                    |   |
|  |   "timestamp": 12.45,                                               |   |
|  |   "audio": { AudioFrame fields },                                   |   |
|  |   "lighting": { LightingFrame fields },                             |   |
|  |   "ald": { AbstractLightingState fields }                           |   |
|  | }                                                                    |   |
|  +---------------------------------------------------------------------+   |
|                                     |                                       |
+=====================================|=======================================+
                                      |
                                      v
+============================================================================+
| MODEL TRAINING LAYER                                                        |
|                                                                             |
|  +---------------------------+    +-----------------------------+           |
|  | Pre-training              |    | Fine-tuning                 |           |
|  | - Self-supervised         |    | - Audio -> ALD prediction   |           |
|  | - Contrastive (CLIP-style)|    | - Supervised on video data  |           |
|  | - Masked prediction       |    | - + human operator data     |           |
|  +-------------+-------------+    +---------------+-------------+           |
|                |                                  |                         |
|                +----------------------------------+                         |
|                               |                                             |
|                               v                                             |
|                  +---------------------------+                              |
|                  | Audio-to-Lighting Model   |                              |
|                  | (15M param Transformer)   |                              |
|                  | Real-time @ 40fps         |                              |
|                  +---------------------------+                              |
|                                                                             |
+============================================================================+

INFERENCE (LIVE SHOW)
+============================================================================+
|                                                                             |
|  Audio Input --> BeatNet + HuBERT --> Audio-to-Lighting Model              |
|                                              |                              |
|                                              v                              |
|                                         ALD Output                          |
|                                              |                              |
|                                              v                              |
|                                      Rig Adapter                            |
|                                     (18 fixtures)                           |
|                                              |                              |
|                                              v                              |
|                                    DMX Frame (512 ch)                       |
|                                              |                              |
|                                              v                              |
|                                    ArtNet Output                            |
|                                    (0.0.0.0:6454)                           |
|                                                                             |
+============================================================================+
```

### 7.2 Specific Models and Tools

| Component | Model/Tool | Source | Purpose |
|---|---|---|---|
| Fixture detection | YOLOv9-c (fine-tuned) | `ultralytics` (already in project) | Detect fixtures in frames |
| Light segmentation | SAM2 (Hiera-L) | `https://github.com/facebookresearch/sam2` | Segment light regions |
| Object tracking | DeepSORT | `https://github.com/levan92/deep_sort_realtime` | Track fixtures across frames |
| Optical flow | RAFT | `https://github.com/princeton-vl/RAFT` | Track beam movement |
| Depth estimation | Depth Anything V2 | `https://github.com/DepthAnything/Depth-Anything-V2` | Single-view layout estimation |
| Beat detection | BeatNet | Already loaded in `model_manager.py` | Beat and BPM from audio |
| Mood classification | HuBERT | Already loaded in `model_manager.py` | Valence/arousal from audio |
| Video backbone | ConvNeXt-Base | `timm` library | Frame feature extraction |
| Temporal model | Transformer (custom) | PyTorch | Sequence modeling |
| Effect classification | TCN | PyTorch | Classify lighting effects |
| Audio-visual matching | CLIP-style contrastive | PyTorch | Learn audio-lighting correspondence |
| Video download | yt-dlp | `https://github.com/yt-dlp/yt-dlp` | Download source footage |
| Frame extraction | ffmpeg | `https://ffmpeg.org/` | Extract frames and audio |
| Annotation | Label Studio | `https://labelstud.io/` | Human annotation interface |
| Rendering (validation) | Mitsuba 3 | `https://github.com/mitsuba-renderer/mitsuba3` | Inverse rendering validation |

### 7.3 Training Procedure Step by Step

**Phase 1: Data Collection (Weeks 1-3)**
1. Set up `yt-dlp` pipeline to download 500 concert videos across genres.
2. Run quality filter; expect ~60% pass rate = 300 videos.
3. Extract frames at 10fps (sufficient for lighting analysis; 30fps for movement).
4. Extract audio tracks at 44100Hz.

**Phase 2: Fine-tune Fixture Detector (Weeks 2-4)**
1. Manually annotate 3,000 frames with fixture bounding boxes using CVAT.
2. Fine-tune YOLOv9 on concert fixture dataset.
3. Validate on held-out 500 frames; target mAP@0.5 > 0.70.
4. Deploy as updated `ml_models/yolov9/model.pt`.

**Phase 3: Build Feature Extraction Pipeline (Weeks 3-6)**
1. Implement `VideoFeatureExtractor` class (Section 7.5).
2. Implement color extraction, brightness estimation, movement tracking.
3. Implement camera motion compensation and exposure normalization.
4. Implement strobe detection.
5. Process 10 test videos end-to-end; visually validate extracted features.

**Phase 4: Generate Training Dataset (Weeks 5-8)**
1. Run full extraction pipeline on all 300 videos.
2. Generate Abstract Lighting Descriptions for each frame.
3. Pair with audio features (BeatNet + HuBERT).
4. Export in TrainingRecorder-compatible JSONL format.
5. Expected dataset size: ~500,000 training frames (300 videos x 5 min avg x 10 fps / 2 for filtering).

**Phase 5: Train Audio-to-Lighting Model (Weeks 7-10)**
1. Pre-train with self-supervised objectives (masked prediction + contrastive).
2. Fine-tune on video-extracted ALD targets.
3. Incorporate any human operator data from existing `TrainingRecorder` sessions.
4. Evaluate using held-out videos: does the model produce lighting that matches the video?

**Phase 6: Integration and Inference (Weeks 9-12)**
1. Export trained model in ONNX or TorchScript format.
2. Integrate into `ModelManager` as a new model type.
3. Build `RigAdapter` for the 18-fixture demo rig.
4. Run real-time inference at 40fps (matching `DMX_FPS`).
5. A/B test: model-generated lighting vs. human operator on blind listening test.

### 7.4 New Modules Needed

```
backend/app/services/ml/
    model_manager.py                 # MODIFY: add video_encoder and lighting_model
    training_recorder.py             # MODIFY: add ALD support
    __init__.py

    # NEW FILES:
    video_pipeline/
        __init__.py
        video_downloader.py          # yt-dlp wrapper, quality filter
        frame_extractor.py           # ffmpeg frame/audio extraction
        fixture_detector.py          # YOLOv9 fine-tuning + inference
        light_segmenter.py           # SAM2 / U-Net light segmentation
        fixture_tracker.py           # DeepSORT multi-fixture tracking
        color_extractor.py           # K-Means HSV color extraction
        brightness_estimator.py      # Exposure-normalized brightness
        movement_tracker.py          # Beam angle + optical flow tracking
        strobe_detector.py           # Rapid brightness change detection
        camera_compensator.py        # Motion compensation + cut detection
        exposure_normalizer.py       # Reference-based exposure normalization
        layout_estimator.py          # 3D rig layout from video

    feature_extraction/
        __init__.py
        ald_generator.py             # Abstract Lighting Description generator
        effect_classifier.py         # TCN-based effect classification
        zone_mapper.py               # 9-zone stage abstraction

    training/
        __init__.py
        video_dataset.py             # PyTorch Dataset for video-extracted data
        audio_lighting_model.py      # Stage 2 transformer model
        contrastive_model.py         # Audio-visual CLIP-style model
        rig_adapter.py               # ALD -> DMX conversion
        train_pipeline.py            # Training orchestration
        evaluate.py                  # Evaluation metrics

ml_models/
    video_encoder/                   # Stage 1 model weights
        config.yaml
        model.pt
    lighting_model/                  # Stage 2 model weights
        config.yaml
        model.pt
        model.onnx                   # Optimized for inference

datasets/
    concert_fixtures/                # YOLO fine-tuning dataset
        data.yaml
        images/
        labels/
    video_extracted/                 # Processed training data
        metadata.json
        *.jsonl                      # TrainingFrame format
```

### 7.5 Data Pipeline Code Structure

**Core processing class:**

```python
class VideoFeatureExtractor:
    """
    Main pipeline: Video file -> Extracted features per frame.

    Orchestrates all CV components to produce training data
    compatible with the existing TrainingRecorder format.
    """

    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager

        # CV components
        self.fixture_detector = FixtureDetector(model_manager)
        self.fixture_tracker = FixtureTracker()
        self.color_extractor = ColorExtractor()
        self.brightness_estimator = BrightnessEstimator()
        self.movement_tracker = MovementTracker()
        self.strobe_detector = StrobeDetector()
        self.camera_compensator = CameraCompensator()
        self.exposure_normalizer = ExposureNormalizer()
        self.layout_estimator = LayoutEstimator()

        # Audio analysis (reuse existing)
        self.audio_analyzer = AudioAnalyzer(model_manager)

        # ALD generation
        self.ald_generator = ALDGenerator()

    def process_video(self, video_path: str, output_path: str) -> str:
        """
        Process a single video file into training data.

        Args:
            video_path: Path to input video file
            output_path: Path for output JSONL file

        Returns:
            Path to generated JSONL training data
        """
        # Extract audio
        audio_path = extract_audio(video_path)
        audio_data, sr = load_audio(audio_path)

        # Open video
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Calibrate exposure normalizer on first 30 frames
        calibration_frames = read_frames(cap, 30)
        self.exposure_normalizer.calibrate(calibration_frames)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to start

        # Process frame by frame
        training_frames = []
        prev_frame = None
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / fps

            # Camera motion compensation
            if prev_frame is not None:
                if self.camera_compensator.detect_scene_cut(prev_frame, frame):
                    self.fixture_tracker.reset()
                self.camera_compensator.update(prev_frame, frame)

            # Detect and track fixtures
            detections = self.fixture_detector.detect(frame)
            tracked = self.fixture_tracker.update(frame, detections)

            # Extract per-fixture features
            exposure_factor = self.exposure_normalizer.get_exposure_factor(frame)

            fixture_states = []
            for track_id, track_info in tracked.items():
                region = extract_region(frame, track_info['bbox'])

                color = self.color_extractor.extract(region)
                brightness = self.brightness_estimator.estimate(
                    region, exposure_factor
                )
                movement = self.movement_tracker.get_movement(track_id)

                fixture_states.append({
                    'id': f'fixture_{track_id}',
                    'color_hsv': color,
                    'brightness': brightness,
                    'pan': movement.get('pan', 0),
                    'tilt': movement.get('tilt', 0),
                    'position': track_info['center'],
                    'class': track_info.get('class_name', 'unknown')
                })

            # Detect strobe
            frame_brightness = np.mean(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ) / 255.0
            strobe_active = self.strobe_detector.update(frame_brightness)

            # Audio features for this timestamp
            audio_frame = self.audio_analyzer.analyze_at_timestamp(
                audio_data, sr, timestamp
            )

            # Generate Abstract Lighting Description
            ald = self.ald_generator.generate(
                fixture_states, strobe_active, timestamp
            )

            # Convert to LightingFrame format
            lighting_frame = self._to_lighting_frame(
                fixture_states, ald, timestamp
            )

            # Create TrainingFrame
            training_frame = {
                'timestamp': timestamp,
                'audio': asdict(audio_frame),
                'lighting': asdict(lighting_frame),
                'ald': asdict(ald),
                'metadata': {
                    'source_video': video_path,
                    'frame_idx': frame_idx,
                    'num_fixtures_detected': len(fixture_states),
                    'exposure_factor': exposure_factor,
                    'strobe_active': strobe_active,
                    'scene_cut': self.camera_compensator.last_was_cut
                }
            }

            training_frames.append(training_frame)
            prev_frame = frame
            frame_idx += 1

        cap.release()

        # Write JSONL (same format as TrainingRecorder.export_training_data)
        with open(output_path, 'w') as f:
            for frame in training_frames:
                f.write(json.dumps(frame) + '\n')

        return output_path

    def _to_lighting_frame(self, fixture_states, ald, timestamp):
        """Convert extracted features to LightingFrame format."""
        fixtures = []
        for fs in fixture_states:
            h, s, v = fs['color_hsv']
            r, g, b = hsv_to_rgb(h, s, v)
            fixtures.append({
                'id': fs['id'],
                'pan': fs['pan'],
                'tilt': fs['tilt'],
                'dimmer': fs['brightness'],
                'r': r,
                'g': g,
                'b': b,
            })

        return LightingFrame(
            timestamp=timestamp,
            fixtures=fixtures,
            dmx_frame=[]  # Reconstructed DMX not needed for training
        )
```

### 7.6 Compute and Storage Requirements

**Data collection and processing:**

| Stage | Compute | Storage | Time (300 videos) |
|---|---|---|---|
| Video download | Network I/O | ~1.5 TB raw video | ~24 hours |
| Frame extraction | CPU (ffmpeg) | ~500 GB frames at 10fps | ~8 hours |
| Audio extraction | CPU (ffmpeg) | ~50 GB WAV files | ~2 hours |
| Fixture detection | 1x GPU (YOLOv9) | ~10 GB detections JSON | ~40 hours |
| Feature extraction | 1x GPU + CPU | ~20 GB features JSONL | ~60 hours |
| Audio analysis | CPU (BeatNet) or GPU (HuBERT) | ~5 GB features | ~15 hours |

**Total for data processing:** ~150 GPU-hours, ~2 TB storage.

**Model training:**

| Training Stage | GPU Requirement | Duration | VRAM |
|---|---|---|---|
| YOLOv9 fine-tuning | 1x RTX 4090 | ~12 hours | 16 GB |
| Contrastive pre-training | 1x A100 (or 2x 4090) | ~48 hours | 40 GB |
| Audio-to-Lighting fine-tuning | 1x RTX 4090 | ~24 hours | 16 GB |

**Inference requirements:**

| Component | Hardware | Latency | Notes |
|---|---|---|---|
| Audio analysis (BeatNet + HuBERT) | CPU or GPU | ~5ms | Already implemented |
| Audio-to-Lighting model | CPU (ONNX) or GPU | ~3ms | 15M parameters |
| Rig Adapter | CPU | <1ms | Deterministic mapping |
| **Total per frame** | | **~8ms** | **Fits in 25ms budget (40fps)** |

### 7.7 Integration with Existing TrainingRecorder Format

The extracted training data is designed to be **directly compatible** with the existing `TrainingRecorder` JSONL format:

**Existing format (from `training_recorder.py`):**
```json
{
  "timestamp": 12.45,
  "audio": {
    "timestamp": 12.45,
    "bpm": 128.0,
    "energy": 0.75,
    "bass": 0.85,
    "mid": 0.45,
    "high": 0.30,
    "valence": 0.6,
    "arousal": 0.8,
    "spectral_flux": 0.12,
    "is_beat": true,
    "beat_position": 1,
    "spectrum": [0.1, 0.3]
  },
  "lighting": {
    "timestamp": 12.45,
    "fixtures": [
      {"id": "mover_l1", "pan": 128, "tilt": 200, "dimmer": 0.9, "r": 0.0, "g": 0.2, "b": 1.0}
    ],
    "dmx_frame": [0, 0, 128]
  }
}
```

**Video-extracted format (fully compatible + extended):**
```json
{
  "timestamp": 12.45,
  "audio": {
    "timestamp": 12.45,
    "bpm": 126.0,
    "energy": 0.72,
    "bass": 0.81,
    "mid": 0.43,
    "high": 0.28,
    "valence": 0.55,
    "arousal": 0.78,
    "spectral_flux": 0.10,
    "is_beat": true,
    "beat_position": 1,
    "spectrum": [0.08, 0.25]
  },
  "lighting": {
    "timestamp": 12.45,
    "fixtures": [
      {"id": "fixture_0", "pan": 135, "tilt": 190, "dimmer": 0.85, "r": 0.05, "g": 0.18, "b": 0.95},
      {"id": "fixture_1", "pan": 120, "tilt": 195, "dimmer": 0.82, "r": 0.02, "g": 0.15, "b": 0.98}
    ],
    "dmx_frame": []
  },
  "ald": {
    "overall_intensity": 0.83,
    "dominant_color": [230, 0.92, 0.95],
    "secondary_color": [180, 0.65, 0.70],
    "color_spread": 0.3,
    "intensity_map": [0.8, 0.9, 0.8, 0.5, 0.7, 0.5, 0.3, 0.4, 0.3],
    "movement_type": "horizontal_sweep",
    "movement_speed": 0.5,
    "movement_amplitude": 0.6,
    "movement_phase_spread": 0.8,
    "active_effects": ["beat_sync"],
    "effect_intensity": 0.7,
    "energy_level": "high",
    "structure_position": "peak",
    "group_mode": "all",
    "group_contrast": 0.2
  },
  "metadata": {
    "source_video": "concert_edm_001.mp4",
    "frame_idx": 3735,
    "num_fixtures_detected": 24,
    "exposure_factor": 1.05,
    "strobe_active": false
  }
}
```

The `audio` and `lighting` fields match the existing `AudioFrame` and `LightingFrame` dataclasses exactly. The `ald` and `metadata` fields are extensions that the training pipeline uses but that the existing `TrainingRecorder` can ignore.

**To load both human-recorded and video-extracted data:**
```python
def load_training_data(paths: List[str]) -> List[TrainingFrame]:
    """Load training data from multiple JSONL files (human + video-extracted)."""
    frames = []
    for path in paths:
        with open(path) as f:
            for line in f:
                data = json.loads(line)
                audio = AudioFrame(**data['audio'])
                lighting = LightingFrame(**data['lighting'])
                frames.append(TrainingFrame(
                    timestamp=data['timestamp'],
                    audio=audio,
                    lighting=lighting
                ))
    return frames
```

---

## 8. Challenges and Mitigations

### 8.1 Camera Perspective vs. Actual Fixture Output

**Challenge:** The camera sees the scene from one angle. A fixture pointing at the camera appears much brighter than the same fixture pointing away. The actual DMX output is identical in both cases.

**Mitigations:**
1. **Multiple camera angles:** When available, average fixture estimates across angles.
2. **Beam direction awareness:** If a beam is pointing toward the camera, apply a correction factor to reduce estimated intensity:
   ```python
   # Estimate beam direction from beam line segment
   beam_toward_camera = beam_angle_relative_to_camera(beam_vector, camera_vector)
   if beam_toward_camera > 0.8:  # Nearly pointing at camera
       intensity_correction = 0.5  # Halve the estimated intensity
   ```
3. **Focus on relative changes:** Instead of estimating absolute DMX values, focus on relative changes between frames. A fixture going from dim to bright (relative) maps to a dimmer ramp regardless of absolute perceived brightness.

### 8.2 Color Accuracy

**Challenge:** Camera color science differs from LED fixture color science. A deep blue LED may appear purple on camera.

**Mitigations:**
1. **Calibration dataset:** Create a small dataset of known LED colors (from a real fixture) captured on various cameras. Train a small MLP to map camera RGB to LED RGB.
2. **Hue prioritization:** Even if absolute colors are wrong, the hue relationships are usually preserved (blue is still blueish). The system learns "this audio goes with a blue-ish color" rather than exact DMX values.
3. **Color palette classification:** Instead of exact RGB, classify into the existing `ColorPalette` enum (EDM, ROCK, AMBIENT, etc.) and the `COLOR_PRESETS`. Palette-level accuracy is easier to achieve than pixel-level accuracy.

### 8.3 Fixture Identification

**Challenge:** In a wide shot, it is hard to determine exactly which fixture produces which light. Multiple fixtures of the same type may look identical.

**Mitigations:**
1. **Group-level analysis:** Instead of individual fixture identification, analyze groups (left side, right side, truss, floor). This aligns with the `FixtureGroupManager` groups.
2. **Zone-based abstraction:** The 9-zone ALD representation (Section 3.5) sidesteps the individual fixture identification problem entirely.
3. **Consistent tracking:** DeepSORT with appearance features maintains identity within a single camera shot. Across shots, re-identification uses position consistency.

### 8.4 Scaling from Professional Shows to Small Venues

**Challenge:** Professional shows use 200+ fixtures with complex rigging. A small venue might have 8 LED pars.

**Mitigations:**
1. **Abstract Lighting Description:** The ALD is rig-agnostic by design. "Warm wash from the left, cool wash from the right" works with 200 fixtures or 4.
2. **Progressive detail:** With fewer fixtures, the model reduces detail:
   - 200 fixtures: full 9-zone resolution, individual chases, complex patterns
   - 18 fixtures: 9-zone resolution, group-based chases
   - 8 fixtures: simplified to 4-zone (left, right, front, back), basic patterns
   - 4 fixtures: 2-zone (side A, side B), color and intensity only
3. **Fixture capability awareness:** The `RigAdapter` knows which fixtures have pan/tilt (movers) vs. color-only (pars). Movement information is only applied to capable fixtures.

### 8.5 Real-Time Inference Requirements

**Challenge:** The model must produce DMX output at 40fps (25ms per frame) to match `DMX_FPS` in `config.py`.

**Mitigations:**
1. **Small model:** The Stage 2 model (15M parameters) is designed for real-time inference.
2. **ONNX Runtime:** Export the model to ONNX format and use ONNX Runtime for optimized CPU inference.
3. **Quantization:** INT8 quantization reduces model size by 4x and increases speed by 2-3x with minimal quality loss.
4. **Batch prediction:** Predict 4 frames ahead and interpolate, reducing model calls to 10fps while outputting at 40fps.

```python
# Integration in model_manager.py
async def _load_lighting_model(self):
    """Load the trained audio-to-lighting model."""
    model_path = Path("ml_models/lighting_model/model.onnx")
    if not model_path.exists():
        print("Audio-to-Lighting model not found")
        return

    try:
        import onnxruntime as ort

        self.models['lighting'] = ort.InferenceSession(
            str(model_path),
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        print("Audio-to-Lighting model loaded successfully")
    except Exception as e:
        print(f"Lighting model loading error: {e}")
```

### 8.6 Additional Challenges

| Challenge | Severity | Mitigation |
|---|---|---|
| Audience phone recordings (shaky, low quality) | Medium | Quality filter removes; only ~10% of YouTube footage |
| LED screens on stage confused with fixtures | High | Train fixture detector to distinguish screens; screens have video content, fixtures have solid/gradual color |
| Fog machines create transient beams | Low | Track persistence; real beams last >0.5s, fog wisps are transient |
| Laser effects misidentified as beam lights | Medium | Laser class in YOLO config; lasers have distinct thin beam and scanning pattern |
| Audio-video sync drift in source material | Medium | Re-sync using onset detection in both audio and video (flash = beat) |
| Different fixture types produce different colors from same DMX | Medium | ALD operates on perceived color, not DMX; rig adapter handles fixture-specific mapping |

---

## 9. Integration with Existing Codebase

### 9.1 Files to Modify

**`backend/app/services/ml/model_manager.py`**
- Add `_load_lighting_model()` method for the trained audio-to-lighting model.
- Add `predict_lighting()` method that takes `AudioFrame` and returns `LightingFrame`.
- Add `_load_video_encoder()` method for Stage 1 (offline processing only).

**`backend/app/services/ml/training_recorder.py`**
- Extend `TrainingFrame` to include optional `ald: AbstractLightingState` field.
- Add `import_video_extracted_data()` class method to load video-extracted JSONL files.
- Add validation that video-extracted data conforms to expected schema.

**`backend/app/services/effects/effects_engine.py`**
- Add `ml_mode` to `EffectsConfig` (alongside `auto_mode` and manual LFO mode).
- In `_update_fixtures()`, add a branch for ML model output:
  ```python
  if self.config.ml_mode and self.model_manager.has_model('lighting'):
      ml_output = await self.model_manager.predict_lighting(audio_features)
      self._apply_ml_output(ml_output)
  ```

**`backend/app/core/config.py`**
- Add `LIGHTING_MODEL_PATH` setting alongside existing model paths.
- Add `VIDEO_PIPELINE_OUTPUT_DIR` for extracted training data.

### 9.2 New Configuration

```python
# In config.py
LIGHTING_MODEL_PATH: str = "ml_models/lighting_model/model.onnx"
VIDEO_PIPELINE_OUTPUT_DIR: str = "ml_training_data/video_extracted"
VIDEO_PIPELINE_FRAME_RATE: int = 10  # Extract at 10fps for training
VIDEO_PIPELINE_MIN_QUALITY: float = 0.5
```

### 9.3 API Endpoints (New)

```python
# Video pipeline management endpoints
POST /api/v1/ml/video-pipeline/process
    Body: { "video_url": "...", "genre": "edm" }
    Response: { "job_id": "...", "status": "queued" }

GET /api/v1/ml/video-pipeline/status/{job_id}
    Response: { "status": "processing", "progress": 0.45, "frames_extracted": 1350 }

GET /api/v1/ml/video-pipeline/datasets
    Response: { "datasets": [{ "name": "edm_2024", "frames": 150000, "hours": 4.2 }] }

POST /api/v1/ml/train
    Body: { "datasets": ["edm_2024", "rock_2024"], "epochs": 50 }
    Response: { "job_id": "...", "status": "training" }

POST /api/v1/ml/inference/enable
    Body: { "model": "lighting_v1", "rig": "demo_18" }
    Response: { "status": "enabled", "latency_ms": 8 }
```

---

## 10. Proof of Concept Plan

### Smallest Viable Experiment

**Goal:** Validate that video-extracted lighting data, when paired with audio, produces training signal useful for an audio-to-lighting model.

**Scope:** 10 videos, color extraction only (no movement tracking), simple MLP model.

**Steps:**

1. **Day 1-2: Data collection**
   - Download 10 high-quality concert videos from YouTube (5 EDM, 5 rock).
   - Extract audio (44100Hz WAV) and frames (10fps JPEG) using ffmpeg.
   - Total: ~50 minutes of footage, ~30,000 frames.

2. **Day 3-4: Color extraction**
   - For each frame, compute the dominant color using K-Means (K=3) on the top 20% brightest pixels.
   - Compute average frame brightness (proxy for overall dimmer).
   - Output: per-frame `(timestamp, dominant_h, dominant_s, dominant_v, brightness)`.

3. **Day 4-5: Audio feature extraction**
   - Run BeatNet for beat detection (using existing `model_manager.py`).
   - Run librosa for energy, bass, mid, high extraction.
   - Run HuBERT for valence/arousal (using existing `model_manager.py`).
   - Output: per-frame `AudioFrame` in existing format.

4. **Day 5-6: Training**
   - Train a simple 3-layer MLP:
     - Input: 12 audio features (from `AudioFrame`)
     - Output: 4 values (dominant_h, dominant_s, dominant_v, brightness)
     - Loss: MSE on normalized outputs
   - Train/val split: 8 videos for training, 2 for validation.

5. **Day 7: Evaluation**
   - On held-out videos, compare model-predicted lighting to video-extracted ground truth.
   - Metrics: color hue accuracy (circular mean error), brightness correlation (Pearson r).
   - **Success criteria:**
     - Hue error < 30 degrees on average (the model picks approximately the right color family)
     - Brightness correlation > 0.5 (the model responds to energy changes)
     - Genre discrimination: EDM colors differ from rock colors

6. **Day 7: Visual demo**
   - Apply model output to the 18-fixture demo rig in the Three.js visualizer.
   - Play one of the held-out audio tracks and observe if the generated lighting "feels right."

**Expected outcome:** Even this minimal POC should demonstrate that video footage contains extractable signal about what lighting "goes with" certain music. The color choices should be broadly genre-appropriate (EDM = cooler colors, rock = warmer) and the brightness should follow energy dynamics.

**Resources needed:**
- 1 workstation with GPU (RTX 3060 or better)
- ~50 GB disk space
- ~1 week of development time
- No additional dependencies beyond what is already in the project (`ultralytics`, `transformers`, `librosa`, `opencv-python`, `numpy`, `torch`)

### Scaling from POC to Full System

After validating the POC, scale up in priority order:

| Priority | Capability | Adds |
|---|---|---|
| P0 (POC) | Color extraction + brightness | Basic genre-appropriate colors |
| P1 | Movement tracking + beam detection | Pan/tilt control for movers |
| P2 | Strobe and effect detection | Dynamic effects, drops, builds |
| P3 | Multi-fixture tracking + zones | Spatial distribution, chases |
| P4 | Full ALD generation | Rig-agnostic representation |
| P5 | Contrastive pre-training | Better audio-lighting alignment |
| P6 | Inverse rendering validation | Ground truth refinement |
| P7 | 10,000+ video dataset | Production-quality model |

---

## Appendix A: Key Papers and References

1. **SAM2 (Segment Anything Model 2)** -- Ravi et al., 2024. Meta AI. Promptable segmentation for images and video. `https://github.com/facebookresearch/sam2`

2. **RAFT (Recurrent All-Pairs Field Transforms for Optical Flow)** -- Teed and Deng, ECCV 2020. State-of-the-art optical flow for movement tracking. `https://github.com/princeton-vl/RAFT`

3. **Depth Anything V2** -- Yang et al., 2024. Monocular depth estimation for layout reconstruction. `https://github.com/DepthAnything/Depth-Anything-V2`

4. **BeatNet** -- Heydari and Cwitkowitz, 2021. Real-time beat and downbeat tracking. Already integrated in `model_manager.py`.

5. **DeepSORT** -- Wojke et al., 2017. Multi-object tracking with deep association metrics. `https://github.com/levan92/deep_sort_realtime`

6. **CLIP (Contrastive Language-Image Pre-training)** -- Radford et al., ICML 2021. Foundation for audio-visual contrastive learning approach.

7. **Temporal Convolutional Networks** -- Lea et al., CVPR 2017. For effect classification and temporal segmentation.

8. **Mitsuba 3** -- Jakob et al., 2022. Differentiable renderer for inverse rendering validation. `https://github.com/mitsuba-renderer/mitsuba3`

9. **ConvNeXt** -- Liu et al., CVPR 2022. Modern CNN backbone for frame feature extraction. Available in `timm` library.

10. **Neural Inverse Rendering** -- Kaya et al., ICML 2022. Recovering light parameters from images.

11. **YOLOv9** -- Wang et al., 2024. Object detection backbone already in the project. `https://github.com/ultralytics/ultralytics`

12. **HuBERT** -- Hsu et al., 2021. Self-supervised speech representation for emotion classification. Already integrated in `model_manager.py`.

## Appendix B: Glossary

| Term | Definition |
|---|---|
| ALD | Abstract Lighting Description -- rig-independent representation of lighting intent |
| CCM | Camera Color Correction Matrix -- transforms camera RGB to standardized color space |
| DMX | Digital Multiplex -- industry standard protocol for lighting control (512 channels per universe) |
| GDTF | General Device Type Format -- standard for describing fixture capabilities |
| LD | Lighting Designer |
| LFO | Low Frequency Oscillator -- used for periodic lighting effects |
| SfM | Structure from Motion -- reconstructing 3D from multiple 2D views |
| TCN | Temporal Convolutional Network -- 1D CNN for sequence processing |

## Appendix C: Estimated Timeline

```
Week 1-2:   Data collection infrastructure (downloader, quality filter, extraction)
Week 2-3:   POC - color extraction + simple model (validate approach)
Week 3-4:   Fine-tune YOLOv9 for concert fixtures
Week 4-6:   Full feature extraction pipeline (color, brightness, movement, strobe)
Week 6-7:   Abstract Lighting Description generator
Week 7-8:   Process full video dataset (300+ videos)
Week 8-10:  Train audio-to-lighting transformer
Week 10-11: Integration into EffectsEngine (ml_mode)
Week 11-12: Evaluation, tuning, demo
```

**Total: ~12 weeks from start to integrated demo.**
