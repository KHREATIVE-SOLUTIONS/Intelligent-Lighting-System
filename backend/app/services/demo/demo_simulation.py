"""
Demo Simulation Mode
Generates synthetic audio analysis data to showcase the professional lighting
system without requiring live audio input.

Simulates a complete set progression with configurable genre and speed.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Dict, List


class DemoPhase(Enum):
    """Phases in the demo set simulation."""
    INTRO = "intro"
    VERSE = "verse"
    BUILDUP_1 = "buildup_1"
    PRE_DROP_BLACKOUT = "pre_drop_blackout"
    DROP_1 = "drop_1"
    SUSTAIN = "sustain"
    BREAKDOWN = "breakdown"
    BUILDUP_2 = "buildup_2"
    DROP_2 = "drop_2"
    OUTRO = "outro"
    FINISHED = "finished"


@dataclass
class DemoPhaseConfig:
    """Configuration for a single demo phase."""
    phase: DemoPhase
    duration: float          # seconds
    section: str             # SongSection value
    energy_start: float      # Starting energy (0-1)
    energy_end: float        # Ending energy (0-1)
    bass_multiplier: float   # Bass relative to energy
    mid_multiplier: float
    high_multiplier: float
    valence: float           # Mood valence
    arousal: float           # Mood arousal
    beat_active: bool        # Whether beats fire
    spectral_flux: float     # Rate of spectral change
    bpm: float = 128.0


# EDM demo set timeline (6 minutes)
EDM_TIMELINE: List[DemoPhaseConfig] = [
    DemoPhaseConfig(DemoPhase.INTRO, 30.0, "intro",
                    0.1, 0.25, 0.3, 0.2, 0.1, 0.3, 0.2, True, 0.05, 128.0),
    DemoPhaseConfig(DemoPhase.VERSE, 60.0, "verse",
                    0.35, 0.55, 0.6, 0.5, 0.3, 0.5, 0.4, True, 0.1, 128.0),
    DemoPhaseConfig(DemoPhase.BUILDUP_1, 30.0, "buildup",
                    0.4, 0.85, 0.7, 0.5, 0.6, 0.6, 0.7, True, 0.4, 128.0),
    DemoPhaseConfig(DemoPhase.PRE_DROP_BLACKOUT, 0.5, "buildup",
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, 0.0, 128.0),
    DemoPhaseConfig(DemoPhase.DROP_1, 58.0, "drop",
                    0.95, 0.9, 1.0, 0.6, 0.7, 0.8, 0.9, True, 0.5, 128.0),
    DemoPhaseConfig(DemoPhase.SUSTAIN, 30.0, "chorus",
                    0.8, 0.75, 0.9, 0.6, 0.6, 0.7, 0.8, True, 0.2, 128.0),
    DemoPhaseConfig(DemoPhase.BREAKDOWN, 30.0, "breakdown",
                    0.7, 0.2, 0.3, 0.4, 0.2, 0.4, 0.2, True, 0.05, 128.0),
    DemoPhaseConfig(DemoPhase.BUILDUP_2, 30.0, "buildup",
                    0.3, 0.85, 0.7, 0.5, 0.6, 0.6, 0.7, True, 0.4, 128.0),
    DemoPhaseConfig(DemoPhase.DROP_2, 60.0, "drop",
                    0.95, 0.85, 1.0, 0.6, 0.7, 0.8, 0.9, True, 0.5, 128.0),
    DemoPhaseConfig(DemoPhase.OUTRO, 30.0, "outro",
                    0.5, 0.05, 0.3, 0.2, 0.1, 0.2, 0.1, True, 0.02, 128.0),
]

# Genre-specific BPM and mood defaults
GENRE_DEMO_DEFAULTS: Dict[str, Dict] = {
    "edm": {"bpm": 128.0, "valence_offset": 0.1, "arousal_offset": 0.2},
    "rock": {"bpm": 120.0, "valence_offset": 0.0, "arousal_offset": 0.1},
    "pop": {"bpm": 115.0, "valence_offset": 0.2, "arousal_offset": 0.0},
    "hip_hop": {"bpm": 90.0, "valence_offset": -0.1, "arousal_offset": 0.0},
    "jazz": {"bpm": 100.0, "valence_offset": 0.1, "arousal_offset": -0.2},
}


@dataclass
class DemoConfig:
    """Configuration for the demo simulation."""
    genre: str = "edm"
    speed: float = 1.0     # 1.0=realtime, 2.0=double speed, 0.5=half speed
    loop: bool = False      # Loop back to start when finished


class DemoSimulation:
    """
    Generates synthetic audio analysis data for demo/preview mode.
    Feeds data into the effects engine to showcase professional lighting
    without requiring actual audio input.
    """

    def __init__(self, config: DemoConfig = None):
        self.config = config or DemoConfig()
        self._running = False
        self._start_time: float = 0.0
        self._elapsed: float = 0.0
        self._phase_index: int = 0
        self._phase_start_time: float = 0.0
        self._beat_count: int = 0
        self._last_beat_time: float = 0.0

        # Build timeline from genre defaults
        self._timeline = self._build_timeline()
        self._total_duration = sum(p.duration for p in self._timeline)

    def _build_timeline(self) -> List[DemoPhaseConfig]:
        """Build genre-adjusted timeline."""
        defaults = GENRE_DEMO_DEFAULTS.get(self.config.genre, GENRE_DEMO_DEFAULTS["edm"])
        bpm = defaults["bpm"]
        val_offset = defaults["valence_offset"]
        aro_offset = defaults["arousal_offset"]

        timeline = []
        for base in EDM_TIMELINE:
            adjusted = DemoPhaseConfig(
                phase=base.phase,
                duration=base.duration,
                section=base.section,
                energy_start=base.energy_start,
                energy_end=base.energy_end,
                bass_multiplier=base.bass_multiplier,
                mid_multiplier=base.mid_multiplier,
                high_multiplier=base.high_multiplier,
                valence=max(0.0, min(1.0, base.valence + val_offset)),
                arousal=max(0.0, min(1.0, base.arousal + aro_offset)),
                beat_active=base.beat_active,
                spectral_flux=base.spectral_flux,
                bpm=bpm,
            )
            timeline.append(adjusted)
        return timeline

    @property
    def running(self) -> bool:
        return self._running

    @property
    def elapsed(self) -> float:
        return self._elapsed

    @property
    def total_duration(self) -> float:
        return self._total_duration

    @property
    def current_phase(self) -> Optional[DemoPhaseConfig]:
        if 0 <= self._phase_index < len(self._timeline):
            return self._timeline[self._phase_index]
        return None

    @property
    def progress(self) -> float:
        """Overall progress 0-1."""
        if self._total_duration <= 0:
            return 1.0
        return min(1.0, self._elapsed / self._total_duration)

    def start(self):
        """Start the demo simulation."""
        self._running = True
        self._start_time = time.time()
        self._elapsed = 0.0
        self._phase_index = 0
        self._phase_start_time = 0.0
        self._beat_count = 0
        self._last_beat_time = 0.0
        self._timeline = self._build_timeline()
        self._total_duration = sum(p.duration for p in self._timeline)

    def stop(self):
        """Stop the demo simulation."""
        self._running = False

    def set_genre(self, genre: str):
        """Change genre (takes effect on next start or immediately if running)."""
        self.config.genre = genre.lower()
        self._timeline = self._build_timeline()
        self._total_duration = sum(p.duration for p in self._timeline)

    def set_speed(self, speed: float):
        """Set playback speed multiplier."""
        self.config.speed = max(0.25, min(8.0, speed))

    def update(self, delta_time: float) -> Optional[Dict]:
        """
        Advance the simulation and generate synthetic audio analysis data.

        Args:
            delta_time: Real elapsed time since last call

        Returns:
            Dict with synthetic audio data to feed into effects engine, or None if finished.
        """
        if not self._running:
            return None

        # Apply speed multiplier
        sim_delta = delta_time * self.config.speed
        self._elapsed += sim_delta

        # Check phase progression
        phase = self.current_phase
        if phase is None:
            if self.config.loop:
                self.start()
                phase = self.current_phase
            else:
                self._running = False
                return None

        phase_elapsed = self._elapsed - self._phase_start_time
        if phase_elapsed >= phase.duration:
            # Advance to next phase
            self._phase_start_time += phase.duration
            self._phase_index += 1
            if self._phase_index >= len(self._timeline):
                if self.config.loop:
                    self.start()
                else:
                    self._running = False
                    return None
            phase = self.current_phase
            phase_elapsed = self._elapsed - self._phase_start_time

        if phase is None:
            return None

        # Calculate phase progress (0-1)
        phase_progress = min(1.0, phase_elapsed / max(0.01, phase.duration))

        # Interpolate energy
        energy = phase.energy_start + (phase.energy_end - phase.energy_start) * phase_progress

        # Add natural variation (subtle sine wave)
        variation = math.sin(self._elapsed * 2.3) * 0.03 + math.sin(self._elapsed * 5.7) * 0.02
        energy = max(0.0, min(1.0, energy + variation))

        # Frequency bands from energy
        bass = min(1.0, energy * phase.bass_multiplier + math.sin(self._elapsed * 1.5) * 0.05)
        mid = min(1.0, energy * phase.mid_multiplier + math.sin(self._elapsed * 3.1) * 0.03)
        high = min(1.0, energy * phase.high_multiplier + math.sin(self._elapsed * 7.2) * 0.04)

        # Beat generation
        beat_interval = 60.0 / phase.bpm if phase.bpm > 0 else 0.5
        is_beat = False
        if phase.beat_active:
            time_since_beat = self._elapsed - self._last_beat_time
            if time_since_beat >= beat_interval:
                is_beat = True
                self._beat_count += 1
                self._last_beat_time = self._elapsed

        # Spectral flux with buildup ramp
        spectral_flux = phase.spectral_flux
        if phase.phase in (DemoPhase.BUILDUP_1, DemoPhase.BUILDUP_2):
            spectral_flux *= (0.5 + 0.5 * phase_progress)

        return {
            "energy": energy,
            "bass": max(0.0, bass),
            "mid": max(0.0, mid),
            "high": max(0.0, high),
            "is_beat": is_beat,
            "beat_number": self._beat_count,
            "valence": phase.valence,
            "arousal": phase.arousal,
            "spectral_flux": spectral_flux,
            "bpm": phase.bpm,
            "section": phase.section,
            "phase": phase.phase.value,
            "phase_progress": round(phase_progress, 3),
            "overall_progress": round(self.progress, 3),
        }

    def get_status(self) -> Dict:
        """Get current demo simulation status."""
        phase = self.current_phase
        return {
            "running": self._running,
            "genre": self.config.genre,
            "speed": self.config.speed,
            "loop": self.config.loop,
            "elapsed": round(self._elapsed, 1),
            "total_duration": round(self._total_duration, 1),
            "progress": round(self.progress, 3),
            "current_phase": phase.phase.value if phase else "finished",
            "current_section": phase.section if phase else "none",
            "beat_count": self._beat_count,
            "bpm": phase.bpm if phase else 0,
        }
