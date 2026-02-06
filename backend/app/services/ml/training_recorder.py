"""
Training Data Recorder for Skip-BART Style Lighting Model

Records synchronized pairs of:
- Audio features (embeddings, BPM, energy, frequency bands)
- Lighting states (DMX values for all fixtures)

This data is used to train a model that learns to map audio → lighting
like a professional operator would.
"""

import json
import time
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import threading
import queue


@dataclass
class AudioFrame:
    """Audio features for one frame."""
    timestamp: float
    bpm: float
    energy: float
    bass: float
    mid: float
    high: float
    valence: float
    arousal: float
    spectral_flux: float
    is_beat: bool
    beat_position: int
    # Raw spectrum for more detailed analysis
    spectrum: List[float] = field(default_factory=list)


@dataclass
class LightingFrame:
    """Lighting state for one frame."""
    timestamp: float
    fixtures: List[Dict]  # [{id, pan, tilt, dimmer, r, g, b}, ...]
    dmx_frame: List[int]  # Full 512-channel DMX frame


@dataclass
class TrainingFrame:
    """Combined audio + lighting frame for training."""
    timestamp: float
    audio: AudioFrame
    lighting: LightingFrame


class TrainingRecorder:
    """
    Records training data for the lighting ML model.

    Usage:
        recorder = TrainingRecorder()
        recorder.start_recording("session_001")

        # During playback, call these on each frame:
        recorder.record_audio(audio_features)
        recorder.record_lighting(lighting_state)

        recorder.stop_recording()
        recorder.export_training_data("training_data.jsonl")
    """

    def __init__(self, output_dir: str = "ml_training_data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.recording = False
        self.session_name = ""
        self.start_time = 0.0

        # Buffers for current frame data
        self._current_audio: Optional[AudioFrame] = None
        self._current_lighting: Optional[LightingFrame] = None

        # Recorded frames
        self.frames: List[TrainingFrame] = []

        # Recording stats
        self.frame_count = 0
        self.audio_frames = 0
        self.lighting_frames = 0

        # Thread-safe queue for async recording
        self._record_queue = queue.Queue()
        self._record_thread: Optional[threading.Thread] = None

    def start_recording(self, session_name: str = None):
        """Start a new recording session."""
        if self.recording:
            print("Already recording!")
            return

        self.session_name = session_name or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.start_time = time.time()
        self.frames = []
        self.frame_count = 0
        self.audio_frames = 0
        self.lighting_frames = 0
        self.recording = True

        # Start background recording thread
        self._record_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._record_thread.start()

        print(f"[Recorder] Started recording session: {self.session_name}")

    def stop_recording(self) -> int:
        """Stop recording and return frame count."""
        if not self.recording:
            return 0

        self.recording = False

        # Wait for queue to drain
        self._record_queue.join()

        print(f"[Recorder] Stopped recording. Captured {len(self.frames)} frames")
        print(f"[Recorder] Audio frames: {self.audio_frames}, Lighting frames: {self.lighting_frames}")

        return len(self.frames)

    def record_audio(self,
                     bpm: float,
                     energy: float,
                     bass: float,
                     mid: float,
                     high: float,
                     valence: float = 0.5,
                     arousal: float = 0.5,
                     spectral_flux: float = 0.0,
                     is_beat: bool = False,
                     beat_position: int = 1,
                     spectrum: List[float] = None):
        """Record audio features for current frame."""
        if not self.recording:
            return

        frame = AudioFrame(
            timestamp=time.time() - self.start_time,
            bpm=bpm,
            energy=energy,
            bass=bass,
            mid=mid,
            high=high,
            valence=valence,
            arousal=arousal,
            spectral_flux=spectral_flux,
            is_beat=is_beat,
            beat_position=beat_position,
            spectrum=spectrum or []
        )

        self._record_queue.put(("audio", frame))
        self.audio_frames += 1

    def record_lighting(self,
                        fixtures: List[Dict],
                        dmx_frame: List[int] = None):
        """Record lighting state for current frame."""
        if not self.recording:
            return

        frame = LightingFrame(
            timestamp=time.time() - self.start_time,
            fixtures=fixtures,
            dmx_frame=dmx_frame or []
        )

        self._record_queue.put(("lighting", frame))
        self.lighting_frames += 1

    def _recording_loop(self):
        """Background thread for processing recordings."""
        while self.recording or not self._record_queue.empty():
            try:
                item = self._record_queue.get(timeout=0.1)
                frame_type, frame_data = item

                if frame_type == "audio":
                    self._current_audio = frame_data
                elif frame_type == "lighting":
                    self._current_lighting = frame_data

                # When we have both audio and lighting, create training frame
                if self._current_audio and self._current_lighting:
                    # Only pair if timestamps are close (within 50ms)
                    time_diff = abs(self._current_audio.timestamp - self._current_lighting.timestamp)
                    if time_diff < 0.05:
                        training_frame = TrainingFrame(
                            timestamp=self._current_lighting.timestamp,
                            audio=self._current_audio,
                            lighting=self._current_lighting
                        )
                        self.frames.append(training_frame)
                        self.frame_count += 1

                        # Clear for next pair
                        self._current_audio = None
                        self._current_lighting = None

                self._record_queue.task_done()

            except queue.Empty:
                continue

    def export_training_data(self, filename: str = None) -> str:
        """Export recorded data to JSONL format for training."""
        if not self.frames:
            print("[Recorder] No frames to export!")
            return ""

        filename = filename or f"{self.session_name}.jsonl"
        filepath = self.output_dir / filename

        with open(filepath, 'w') as f:
            for frame in self.frames:
                # Convert to dict for JSON serialization
                data = {
                    'timestamp': frame.timestamp,
                    'audio': asdict(frame.audio),
                    'lighting': asdict(frame.lighting)
                }
                f.write(json.dumps(data) + '\n')

        print(f"[Recorder] Exported {len(self.frames)} frames to {filepath}")

        # Also export metadata
        meta_path = self.output_dir / f"{self.session_name}_meta.json"
        metadata = {
            'session_name': self.session_name,
            'total_frames': len(self.frames),
            'duration_seconds': self.frames[-1].timestamp if self.frames else 0,
            'avg_fps': len(self.frames) / self.frames[-1].timestamp if self.frames else 0,
            'created': datetime.now().isoformat(),
            'fixture_count': len(self.frames[0].lighting.fixtures) if self.frames else 0
        }
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        return str(filepath)

    def get_stats(self) -> Dict:
        """Get current recording statistics."""
        duration = time.time() - self.start_time if self.recording else 0
        return {
            'recording': self.recording,
            'session_name': self.session_name,
            'frame_count': self.frame_count,
            'audio_frames': self.audio_frames,
            'lighting_frames': self.lighting_frames,
            'duration_seconds': duration,
            'fps': self.frame_count / duration if duration > 0 else 0
        }


class ManualLightingController:
    """
    Allows manual control of lighting for training data collection.

    The operator uses this to control lights while music plays,
    and the TrainingRecorder captures their decisions.
    """

    def __init__(self, effects_engine):
        self.engine = effects_engine
        self.recorder: Optional[TrainingRecorder] = None

        # Manual override state
        self.manual_mode = False
        self.global_dimmer = 1.0
        self.global_color = (1.0, 1.0, 1.0)  # RGB
        self.movement_pattern = "none"
        self.strobe_active = False

        # Fixture group states
        self.group_states = {
            'all': {'dimmer': 1.0, 'color': (1.0, 1.0, 1.0)},
            'odd': {'dimmer': 1.0, 'color': (1.0, 0.0, 0.0)},
            'even': {'dimmer': 1.0, 'color': (0.0, 0.0, 1.0)},
            'left': {'dimmer': 1.0, 'color': (1.0, 1.0, 1.0)},
            'right': {'dimmer': 1.0, 'color': (1.0, 1.0, 1.0)},
        }

    def attach_recorder(self, recorder: TrainingRecorder):
        """Attach a recorder to capture manual operations."""
        self.recorder = recorder

    def set_manual_mode(self, enabled: bool):
        """Enable/disable manual control mode."""
        self.manual_mode = enabled
        if self.engine:
            self.engine.config.auto_mode = not enabled
        print(f"[Manual Control] {'Enabled' if enabled else 'Disabled'}")

    def set_global_dimmer(self, value: float):
        """Set master dimmer (0-1)."""
        self.global_dimmer = max(0, min(1, value))
        self._apply_to_fixtures()

    def set_global_color(self, r: float, g: float, b: float):
        """Set global color (RGB 0-1)."""
        self.global_color = (
            max(0, min(1, r)),
            max(0, min(1, g)),
            max(0, min(1, b))
        )
        self._apply_to_fixtures()

    def set_color_preset(self, preset: str):
        """Set color from preset name."""
        presets = {
            'white': (1.0, 1.0, 1.0),
            'red': (1.0, 0.0, 0.0),
            'green': (0.0, 1.0, 0.0),
            'blue': (0.0, 0.0, 1.0),
            'cyan': (0.0, 1.0, 1.0),
            'magenta': (1.0, 0.0, 1.0),
            'yellow': (1.0, 1.0, 0.0),
            'orange': (1.0, 0.5, 0.0),
            'purple': (0.5, 0.0, 1.0),
            'pink': (1.0, 0.4, 0.7),
            'amber': (1.0, 0.75, 0.0),
        }
        if preset in presets:
            self.set_global_color(*presets[preset])

    def set_movement(self, pattern: str):
        """Set movement pattern."""
        self.movement_pattern = pattern
        if self.engine:
            from app.services.effects.movement_patterns import MovementType
            pattern_map = {
                'none': MovementType.NONE,
                'circle': MovementType.TRUE_CIRCLE,
                'sweep': MovementType.HORIZONTAL_SWEEP,
                'tilt': MovementType.VERTICAL_SWEEP,
                'figure8': MovementType.FIGURE_8,
                'chase': MovementType.PAN_CHASE,
                'ballyhoo': MovementType.BALLYHOO,
            }
            if pattern in pattern_map:
                self.engine.movement.set_pattern(pattern_map[pattern])

    def trigger_strobe(self, duration: float = 0.5):
        """Trigger a strobe burst."""
        self.strobe_active = True
        if self.engine:
            self.engine.trigger_strobe_burst(duration=duration, frequency=12.0)

    def trigger_blackout(self):
        """Momentary blackout."""
        self.set_global_dimmer(0.0)

    def trigger_flash(self, duration: float = 0.1):
        """Full white flash with auto-reset.

        BUG-033 fix: auto-resets to previous state after duration instead of
        relying on caller (which never did the reset).
        """
        old_color = self.global_color
        old_dimmer = self.global_dimmer
        self.set_global_color(1.0, 1.0, 1.0)
        self.set_global_dimmer(1.0)

        def reset():
            self.global_color = old_color
            self.global_dimmer = old_dimmer
            self._apply_to_fixtures()

        threading.Timer(duration, reset).start()

    def _apply_to_fixtures(self):
        """Apply current manual state to all fixtures."""
        if not self.engine or not self.manual_mode:
            return

        for fixture in self.engine.fixtures.fixtures.values():
            fixture.dimmer = self.global_dimmer
            fixture.red = self.global_color[0]
            fixture.green = self.global_color[1]
            fixture.blue = self.global_color[2]


# Global recorder instance
_global_recorder: Optional[TrainingRecorder] = None


def get_recorder() -> TrainingRecorder:
    """Get or create global recorder instance."""
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = TrainingRecorder()
    return _global_recorder


def set_recorder(recorder: TrainingRecorder):
    """Set global recorder instance."""
    global _global_recorder
    _global_recorder = recorder
