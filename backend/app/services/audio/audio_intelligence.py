"""
Audio Intelligence Service
==========================

Deep audio analysis for intelligent lighting that doesn't rely on lyrics.
Extracts musical meaning from spectral characteristics alone — making it
ideal for electronic music which is 80%+ instrumental.

FOUR ANALYSIS LAYERS:

1. SOUND EVENT DETECTION
   Identifies EDM production elements in real-time:
   - Risers: spectral centroid climbing + noise floor increasing
   - Impacts: sudden broadband transient after low energy
   - Sweeps: filter open/close (spectral centroid moving)
   - White noise builds: high spectral flatness + rising energy
   - Drops: bass impact + energy spike after buildup

2. ENERGY TRAJECTORY
   Tracks not just current energy but WHERE it's going:
   - Building: energy derivative positive over 2-4 bar window
   - Sustaining: energy stable (high or low)
   - Falling: energy derivative negative
   - Anticipation: detects "the calm before the drop"

3. TIMBRAL MOOD (without lyrics)
   Derives mood from spectral shape:
   - Brightness (spectral centroid): dark/gritty → bright/euphoric
   - Noisiness (spectral flatness): tonal/warm → noisy/aggressive
   - Warmth (bass-to-treble ratio): cold/thin → warm/full
   - Density (onset rate): sparse/ambient → dense/driving

4. RHYTHMIC PATTERN ANALYSIS
   Detects groove characteristics:
   - Kick pattern: four-on-the-floor vs half-time vs breakbeat
   - Hi-hat density: sparse (breakdown) → dense (buildup/drop)
   - Onset regularity: how "on-grid" vs syncopated the rhythm is
   - Groove intensity: combined rhythmic drive metric

All outputs are continuous 0-1 signals designed to feed directly into
the effects engine's section detector and lighting parameter modulation.
"""

import math
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SoundEvent:
    """A detected audio event with type and intensity."""
    event_type: str      # "riser", "impact", "sweep_up", "sweep_down", "noise_build", "drop_hit"
    intensity: float     # 0-1 strength
    start_time: float    # when it started
    duration: float      # estimated duration so far
    active: bool = True  # still happening


@dataclass
class EnergyTrajectory:
    """Energy direction and momentum."""
    direction: str = "sustaining"  # "building", "sustaining", "falling", "anticipation"
    momentum: float = 0.0         # how fast (positive=building, negative=falling)
    current: float = 0.5          # current smoothed energy
    target_estimate: float = 0.5  # where energy appears headed
    bars_in_direction: int = 0    # how long this direction has held


@dataclass
class TimbralMood:
    """Mood derived from spectral characteristics."""
    brightness: float = 0.5   # 0=dark, 1=bright (spectral centroid)
    noisiness: float = 0.3    # 0=tonal, 1=noisy (spectral flatness)
    warmth: float = 0.5       # 0=cold/thin, 1=warm/full (bass ratio)
    density: float = 0.5      # 0=sparse, 1=dense (onset rate)
    mood_label: str = "neutral"  # derived mood string for look library
    energy_color: str = "neutral"  # warm/cool/neutral for color biasing


@dataclass
class RhythmicState:
    """Rhythmic pattern analysis."""
    kick_pattern: str = "four_on_floor"  # "four_on_floor", "half_time", "breakbeat", "none"
    hihat_density: float = 0.5    # 0=sparse, 1=dense
    onset_regularity: float = 0.5  # 0=syncopated/loose, 1=tight/quantized
    groove_intensity: float = 0.5  # combined rhythmic drive
    beats_per_bar: int = 4


@dataclass
class AudioIntelligenceState:
    """Combined output of all analysis layers."""
    events: List[SoundEvent] = field(default_factory=list)
    trajectory: EnergyTrajectory = field(default_factory=EnergyTrajectory)
    timbre: TimbralMood = field(default_factory=TimbralMood)
    rhythm: RhythmicState = field(default_factory=RhythmicState)

    # Section evidence boosts (added to effects engine's section probabilities)
    section_evidence: Dict[str, float] = field(default_factory=lambda: {
        "breakdown": 0.0, "verse": 0.0, "buildup": 0.0, "chorus": 0.0, "drop": 0.0
    })

    # Direct modulation signals for lighting
    riser_intensity: float = 0.0      # 0-1, drives lights upward
    impact_flash: float = 0.0         # 0-1, triggers flash/bump
    sweep_position: float = 0.5       # 0-1, maps to color temperature shift
    anticipation_level: float = 0.0   # 0-1, "something is about to happen"
    drop_character_signal: float = 0.0  # 0-1, how much the audio character has changed from buildup→drop
    buildup_tracking_active: bool = False  # whether we're currently tracking a buildup


# ══════════════════════════════════════════════════════════════════════
#  AUDIO INTELLIGENCE ENGINE
# ══════════════════════════════════════════════════════════════════════

class AudioIntelligence:
    """Deep audio analysis for intelligent lighting without lyrics."""

    def __init__(self):
        self.state = AudioIntelligenceState()

        # ── Spectral history for derivative analysis ──
        self._history_len = 200  # ~3.3 seconds at 60fps
        self._energy_history: deque = deque(maxlen=self._history_len)
        self._bass_history: deque = deque(maxlen=self._history_len)
        self._mid_history: deque = deque(maxlen=self._history_len)
        self._high_history: deque = deque(maxlen=self._history_len)
        self._centroid_history: deque = deque(maxlen=self._history_len)
        self._flatness_history: deque = deque(maxlen=self._history_len)
        self._flux_history: deque = deque(maxlen=self._history_len)

        # ── Onset tracking for rhythmic analysis ──
        self._onset_times: deque = deque(maxlen=64)
        self._bass_onset_times: deque = deque(maxlen=32)
        self._high_onset_times: deque = deque(maxlen=32)
        self._prev_bass: float = 0.0
        self._prev_high: float = 0.0
        self._prev_energy: float = 0.0
        self._prev_mid: float = 0.0

        # ── Event tracking ──
        self._active_events: List[SoundEvent] = []
        self._last_impact_time: float = -999.0
        self._riser_accumulator: float = 0.0
        self._sweep_direction: float = 0.0  # positive=up, negative=down

        # ── Buildup→Drop CHARACTER change detection ──
        # Tracks spectral characteristics DURING buildup to detect the moment
        # the drop lands — even when energy delta is small.
        # A drop after buildup has: centroid drops, flatness drops (less noise),
        # bass kicks in hard, riser disappears, onset pattern becomes regular.
        self._buildup_centroid_avg: float = 0.5   # running centroid during buildup
        self._buildup_flatness_avg: float = 0.5   # running flatness during buildup
        self._buildup_bass_avg: float = 0.2       # running bass during buildup
        self._buildup_active: bool = False         # are we tracking a buildup?
        self._buildup_frames: int = 0              # how many frames of buildup tracked
        self._drop_character_signal: float = 0.0   # 0-1 strength of character change

        # ── Smoothed signals ──
        self._smooth_centroid: float = 0.5
        self._smooth_flatness: float = 0.3
        self._smooth_energy: float = 0.5
        self._smooth_bass_ratio: float = 0.5
        self._smooth_onset_rate: float = 0.0
        self._smooth_hihat_rate: float = 0.0
        self._smooth_kick_rate: float = 0.0

        # ── Trajectory tracking ──
        self._trajectory_direction: str = "sustaining"
        self._trajectory_direction_start: float = 0.0
        self._trajectory_momentum: float = 0.0

        # ── Energy derivative (multi-scale) ──
        self._energy_deriv_short: float = 0.0  # ~0.5s window
        self._energy_deriv_long: float = 0.0   # ~2s window

        # Timing
        self._last_update_time: float = 0.0
        self._frame_count: int = 0

    def update(self, energy: float, bass: float, mid: float, high: float,
               spectral_flux: float, is_beat: bool, bpm: float,
               dt: float = 0.016) -> AudioIntelligenceState:
        """Main update — call every frame with current audio features.

        Args:
            energy: Overall RMS energy (0-1)
            bass: Bass band energy (0-1)
            mid: Mid band energy (0-1)
            high: High band energy (0-1)
            spectral_flux: Rate of spectral change (0-1)
            is_beat: Beat detected this frame
            bpm: Current detected BPM
            dt: Delta time since last frame

        Returns:
            AudioIntelligenceState with all analysis results
        """
        now = time.monotonic()
        self._frame_count += 1
        dt = max(0.001, min(0.1, dt))

        # ── Store history ──
        self._energy_history.append(energy)
        self._bass_history.append(bass)
        self._mid_history.append(mid)
        self._high_history.append(high)
        self._flux_history.append(spectral_flux)

        # Derived spectral features
        total_band = bass + mid + high + 0.001
        centroid = (mid * 0.3 + high * 0.7) / total_band  # pseudo spectral centroid
        flatness = 1.0 - abs(bass - high) / (total_band * 0.5 + 0.001)  # pseudo flatness
        flatness = max(0.0, min(1.0, flatness))

        self._centroid_history.append(centroid)
        self._flatness_history.append(flatness)

        # ── Smooth signals ──
        smooth_rate = 6.0
        self._smooth_centroid += (centroid - self._smooth_centroid) * min(1.0, dt * smooth_rate)
        self._smooth_flatness += (flatness - self._smooth_flatness) * min(1.0, dt * smooth_rate)
        self._smooth_energy += (energy - self._smooth_energy) * min(1.0, dt * 4.0)
        bass_ratio = bass / (total_band * 0.33 + 0.001)
        self._smooth_bass_ratio += (min(1.0, bass_ratio) - self._smooth_bass_ratio) * min(1.0, dt * 3.0)

        # ── Run all analysis layers ──
        self._detect_onsets(energy, bass, mid, high, is_beat, now, dt)
        self._analyze_rhythm(bpm, now, dt)
        self._detect_events(energy, bass, mid, high, spectral_flux, centroid, flatness, now, dt)
        self._compute_energy_trajectory(energy, bpm, now, dt)
        self._compute_timbral_mood(dt)
        self._compute_section_evidence(energy, bass, mid, high, bpm, dt)
        self._update_modulation_signals(dt)

        # Store for delta computation next frame
        self._prev_bass = bass
        self._prev_high = high
        self._prev_energy = energy
        self._prev_mid = mid
        self._last_update_time = now

        return self.state

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 1: ONSET DETECTION (feeds rhythmic analysis)
    # ══════════════════════════════════════════════════════════════════

    def _detect_onsets(self, energy: float, bass: float, mid: float,
                       high: float, is_beat: bool, now: float, dt: float):
        """Detect bass onsets (kicks) and high-frequency onsets (hats)."""
        # Bass onset: significant positive jump in bass
        bass_delta = bass - self._prev_bass
        if bass_delta > 0.08 and bass > 0.15:
            # Cooldown: at least 100ms between bass onsets
            if not self._bass_onset_times or (now - self._bass_onset_times[-1]) > 0.1:
                self._bass_onset_times.append(now)

        # High-frequency onset: positive jump in highs (hi-hats, cymbals)
        high_delta = high - self._prev_high
        if high_delta > 0.05 and high > 0.1:
            if not self._high_onset_times or (now - self._high_onset_times[-1]) > 0.05:
                self._high_onset_times.append(now)

        # General onset (any band)
        energy_delta = energy - self._prev_energy
        if energy_delta > 0.06 and energy > 0.1:
            if not self._onset_times or (now - self._onset_times[-1]) > 0.08:
                self._onset_times.append(now)

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 2: RHYTHMIC PATTERN ANALYSIS
    # ══════════════════════════════════════════════════════════════════

    def _analyze_rhythm(self, bpm: float, now: float, dt: float):
        """Analyze kick patterns, hi-hat density, and groove characteristics."""
        rhythm = self.state.rhythm
        window = 4.0  # analyze last 4 seconds

        # ── Kick (bass onset) rate ──
        recent_kicks = [t for t in self._bass_onset_times if now - t < window]
        kick_rate = len(recent_kicks) / window  # kicks per second
        expected_4otf = bpm / 60.0  # four-on-the-floor: 1 kick per beat
        self._smooth_kick_rate += (kick_rate - self._smooth_kick_rate) * min(1.0, dt * 3.0)

        # ── Kick pattern classification ──
        if self._smooth_kick_rate < 0.3:
            rhythm.kick_pattern = "none"
        elif self._smooth_kick_rate < expected_4otf * 0.6:
            rhythm.kick_pattern = "half_time"
        elif self._smooth_kick_rate < expected_4otf * 1.3:
            rhythm.kick_pattern = "four_on_floor"
        else:
            rhythm.kick_pattern = "breakbeat"

        # ── Kick regularity (how evenly spaced are the kicks?) ──
        if len(recent_kicks) >= 3:
            intervals = [recent_kicks[i+1] - recent_kicks[i] for i in range(len(recent_kicks)-1)]
            if intervals:
                mean_interval = sum(intervals) / len(intervals)
                if mean_interval > 0:
                    variance = sum((iv - mean_interval)**2 for iv in intervals) / len(intervals)
                    cv = math.sqrt(variance) / (mean_interval + 0.001)
                    # Low CV = regular/quantized, high CV = syncopated/loose
                    rhythm.onset_regularity = max(0.0, min(1.0, 1.0 - cv * 2.0))
                else:
                    rhythm.onset_regularity = 0.5
        else:
            rhythm.onset_regularity = 0.0  # too few kicks to determine

        # ── Hi-hat density ──
        recent_hats = [t for t in self._high_onset_times if now - t < window]
        hat_rate = len(recent_hats) / window
        # Normalize: 0 hats/s = 0, ~8+ hats/s = 1.0 (16th notes at 120bpm)
        target_hihat = min(1.0, hat_rate / 8.0)
        self._smooth_hihat_rate += (target_hihat - self._smooth_hihat_rate) * min(1.0, dt * 3.0)
        rhythm.hihat_density = self._smooth_hihat_rate

        # ── General onset rate (density) ──
        recent_onsets = [t for t in self._onset_times if now - t < window]
        onset_rate = len(recent_onsets) / window
        target_onset_rate = min(1.0, onset_rate / 10.0)
        self._smooth_onset_rate += (target_onset_rate - self._smooth_onset_rate) * min(1.0, dt * 3.0)

        # ── Groove intensity (combined metric) ──
        rhythm.groove_intensity = (
            0.35 * min(1.0, self._smooth_kick_rate / max(0.5, expected_4otf)) +
            0.25 * rhythm.hihat_density +
            0.20 * self._smooth_onset_rate +
            0.20 * rhythm.onset_regularity
        )

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 3: SOUND EVENT DETECTION
    # ══════════════════════════════════════════════════════════════════

    def _detect_events(self, energy: float, bass: float, mid: float,
                       high: float, flux: float, centroid: float,
                       flatness: float, now: float, dt: float):
        """Detect risers, impacts, sweeps, noise builds, and drop hits."""
        events = self._active_events

        # Expire old events
        events[:] = [ev for ev in events if ev.active and (now - ev.start_time) < 16.0]

        # ── RISER DETECTION ──
        # Risers: spectral centroid climbing + energy gradually increasing + noise increasing
        centroid_delta = 0.0
        if len(self._centroid_history) >= 30:
            old_centroid = sum(list(self._centroid_history)[-30:-20]) / 10.0
            new_centroid = sum(list(self._centroid_history)[-10:]) / 10.0
            centroid_delta = new_centroid - old_centroid

        energy_delta_long = 0.0
        if len(self._energy_history) >= 30:
            old_energy = sum(list(self._energy_history)[-30:-20]) / 10.0
            new_energy = sum(list(self._energy_history)[-10:]) / 10.0
            energy_delta_long = new_energy - old_energy

        riser_signal = (
            max(0.0, centroid_delta) * 3.0 +      # centroid climbing
            max(0.0, energy_delta_long) * 2.0 +     # energy rising
            max(0.0, flatness - 0.5) * 1.5          # noisiness increasing
        )

        # Accumulate riser signal with decay
        if riser_signal > 0.3:
            self._riser_accumulator += riser_signal * dt * 2.0
            self._riser_accumulator = min(1.0, self._riser_accumulator)
        else:
            self._riser_accumulator *= max(0.0, 1.0 - dt * 1.5)

        # Start/update riser event
        active_riser = next((ev for ev in events if ev.event_type == "riser" and ev.active), None)
        if self._riser_accumulator > 0.25:
            if active_riser is None:
                riser_ev = SoundEvent("riser", self._riser_accumulator, now, 0.0)
                events.append(riser_ev)
            else:
                active_riser.intensity = self._riser_accumulator
                active_riser.duration = now - active_riser.start_time
        elif active_riser is not None:
            active_riser.active = False

        # ── BUILDUP→DROP CHARACTER CHANGE DETECTION ──
        # This is the KEY to not missing drops. Instead of just looking at
        # energy delta (which can be small when buildup is already loud),
        # we track the SPECTRAL CHARACTER change:
        # Buildup: high centroid (riser), high flatness (noise), low bass
        # Drop:    low centroid (bass heavy), low flatness (tonal), high bass
        #
        # When we see this character inversion, it's a drop — period.

        # Track buildup characteristics when riser is active
        if self._riser_accumulator > 0.2 or (active_riser and active_riser.active):
            if not self._buildup_active:
                self._buildup_active = True
                self._buildup_frames = 0
                self._buildup_centroid_avg = centroid
                self._buildup_flatness_avg = flatness
                self._buildup_bass_avg = bass
            else:
                # Running average of buildup spectral character
                alpha = 0.05  # slow tracking
                self._buildup_centroid_avg += (centroid - self._buildup_centroid_avg) * alpha
                self._buildup_flatness_avg += (flatness - self._buildup_flatness_avg) * alpha
                self._buildup_bass_avg += (bass - self._buildup_bass_avg) * alpha
                self._buildup_frames += 1

        # Detect character change: the moment buildup character → drop character
        character_drop_signal = 0.0
        if self._buildup_active and self._buildup_frames > 15:  # need ~0.25s of buildup data
            # Centroid dropping = riser stopped, bass-heavy content arrived
            centroid_drop = max(0.0, self._buildup_centroid_avg - centroid)
            # Flatness dropping = noise floor collapsed (riser noise gone)
            flatness_drop = max(0.0, self._buildup_flatness_avg - flatness)
            # Bass jumping up relative to buildup average
            bass_jump = max(0.0, bass - self._buildup_bass_avg)
            # Riser disappearing
            riser_collapse = max(0.0, self._buildup_frames / 60.0 * (1.0 - self._riser_accumulator))

            # Combined character change score
            character_drop_signal = (
                centroid_drop * 4.0 +     # centroid plunge is strongest signal
                flatness_drop * 3.0 +     # noise floor collapse
                bass_jump * 3.0 +          # bass kick arriving
                riser_collapse * 1.0       # riser dying
            )
            character_drop_signal = min(1.0, character_drop_signal)

        self._drop_character_signal = character_drop_signal

        # ── IMPACT / DROP HIT DETECTION ──
        # THREE paths to detect a drop hit:
        # 1) Classic: large energy spike + high bass (original)
        # 2) Character change: spectral character inverted from buildup (NEW)
        # 3) Riser death: riser was active and suddenly died + bass present (NEW)
        energy_spike = energy - self._prev_energy
        bass_spike = bass - self._prev_bass
        impact_signal = max(0.0, energy_spike) * 2.0 + max(0.0, bass_spike) * 3.0

        was_quiet = self._smooth_energy < 0.25
        post_riser = self._riser_accumulator > 0.15 or (active_riser and active_riser.active)

        # PATH 1: Classic energy spike detection (original, but LOWERED threshold during buildup)
        classic_threshold = 0.4
        if self._buildup_active:
            classic_threshold = 0.2  # much more sensitive during/right after buildup

        # PATH 2: Character change detection (new — catches drops classic misses)
        character_drop = (
            character_drop_signal > 0.3 and
            bass > 0.2 and
            self._buildup_active
        )

        # PATH 3: Riser death + bass arrival
        # If riser was strongly active and just collapsed, and bass is present
        riser_death_drop = (
            self._buildup_active and
            self._buildup_frames > 30 and  # had a real buildup
            self._riser_accumulator < 0.1 and  # riser died
            bass > 0.2 and  # bass is present
            not (active_riser and active_riser.active)  # riser event ended
        )

        # Combined: any path triggers drop detection
        classic_hit = impact_signal > classic_threshold and bass > 0.2
        drop_detected = (classic_hit or character_drop or riser_death_drop)

        if drop_detected and (now - self._last_impact_time) > 1.0:
            # Determine intensity from strongest signal
            drop_intensity = max(
                min(1.0, impact_signal) if classic_hit else 0.0,
                character_drop_signal if character_drop else 0.0,
                0.7 if riser_death_drop else 0.0
            )
            if post_riser or was_quiet or self._buildup_active:
                drop_intensity = min(1.0, drop_intensity * 1.5)
                events.append(SoundEvent("drop_hit", drop_intensity, now, 0.1))
            else:
                events.append(SoundEvent("impact", drop_intensity, now, 0.1))
            self._last_impact_time = now
            # Kill any active riser (the drop has landed)
            if active_riser and active_riser.active:
                active_riser.active = False
                self._riser_accumulator = 0.0
            # Reset buildup tracking
            self._buildup_active = False
            self._buildup_frames = 0

        # Timeout buildup tracking if no drop after a long time
        elif self._buildup_active and self._buildup_frames > 600:  # ~10 seconds
            self._buildup_active = False
            self._buildup_frames = 0

        # ── FILTER SWEEP DETECTION ──
        # Spectral centroid moving significantly in one direction
        if abs(centroid_delta) > 0.02:
            sweep_dir = 1.0 if centroid_delta > 0 else -1.0
            self._sweep_direction += (sweep_dir - self._sweep_direction) * min(1.0, dt * 5.0)

            active_sweep = next((ev for ev in events if ev.event_type.startswith("sweep") and ev.active), None)
            if abs(self._sweep_direction) > 0.4 and active_sweep is None:
                sweep_type = "sweep_up" if self._sweep_direction > 0 else "sweep_down"
                events.append(SoundEvent(sweep_type, abs(centroid_delta) * 5.0, now, 0.0))
            elif active_sweep:
                active_sweep.duration = now - active_sweep.start_time
                active_sweep.intensity = min(1.0, abs(centroid_delta) * 5.0)
                if abs(centroid_delta) < 0.008:
                    active_sweep.active = False
        else:
            self._sweep_direction *= max(0.0, 1.0 - dt * 3.0)
            for ev in events:
                if ev.event_type.startswith("sweep") and ev.active:
                    ev.active = False

        # ── NOISE BUILD DETECTION ──
        # High spectral flatness + rising energy = white noise build
        active_noise = next((ev for ev in events if ev.event_type == "noise_build" and ev.active), None)
        if flatness > 0.6 and energy_delta_long > 0.02 and high > mid * 0.5:
            noise_intensity = min(1.0, (flatness - 0.4) * 2.0 * max(0.0, energy_delta_long) * 5.0)
            if noise_intensity > 0.15:
                if active_noise is None:
                    events.append(SoundEvent("noise_build", noise_intensity, now, 0.0))
                else:
                    active_noise.intensity = noise_intensity
                    active_noise.duration = now - active_noise.start_time
        elif active_noise:
            active_noise.active = False

        self._active_events = events
        self.state.events = [ev for ev in events if ev.active]

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 4: ENERGY TRAJECTORY
    # ══════════════════════════════════════════════════════════════════

    def _compute_energy_trajectory(self, energy: float, bpm: float,
                                   now: float, dt: float):
        """Track energy direction: building, sustaining, falling, anticipation."""
        traj = self.state.trajectory
        traj.current = self._smooth_energy

        # Multi-scale energy derivative
        if len(self._energy_history) >= 15:
            # Short window (~0.5s): recent 15 frames split in half
            hist = list(self._energy_history)
            short_old = sum(hist[-15:-8]) / 7.0
            short_new = sum(hist[-7:]) / 7.0
            self._energy_deriv_short = short_new - short_old

        if len(self._energy_history) >= 60:
            hist = list(self._energy_history)
            long_old = sum(hist[-60:-30]) / 30.0
            long_new = sum(hist[-30:]) / 30.0
            self._energy_deriv_long = long_new - long_old

        # Combined momentum (weighted toward long-term for stability)
        momentum = self._energy_deriv_short * 0.3 + self._energy_deriv_long * 0.7
        self._trajectory_momentum += (momentum - self._trajectory_momentum) * min(1.0, dt * 4.0)
        traj.momentum = self._trajectory_momentum

        # ── Direction classification ──
        prev_direction = self._trajectory_direction

        if self._trajectory_momentum > 0.015:
            new_direction = "building"
        elif self._trajectory_momentum < -0.015:
            new_direction = "falling"
        elif self._smooth_energy < 0.12 and self._energy_deriv_long > -0.005:
            # Very low energy, not falling further = anticipation (calm before storm)
            new_direction = "anticipation"
        else:
            new_direction = "sustaining"

        # Track direction changes
        if new_direction != prev_direction:
            self._trajectory_direction = new_direction
            self._trajectory_direction_start = now
        traj.direction = self._trajectory_direction

        # Bars in current direction
        beats_per_sec = bpm / 60.0
        secs_in_dir = now - self._trajectory_direction_start
        traj.bars_in_direction = int(secs_in_dir * beats_per_sec / 4.0)

        # Target estimate: where is energy headed?
        look_ahead = self._smooth_energy + self._trajectory_momentum * 3.0
        traj.target_estimate = max(0.0, min(1.0, look_ahead))

    # ══════════════════════════════════════════════════════════════════
    #  TIMBRAL MOOD (without lyrics)
    # ══════════════════════════════════════════════════════════════════

    def _compute_timbral_mood(self, dt: float):
        """Derive mood from spectral characteristics alone."""
        timbre = self.state.timbre

        timbre.brightness = self._smooth_centroid
        timbre.noisiness = self._smooth_flatness
        timbre.warmth = self._smooth_bass_ratio
        timbre.density = self._smooth_onset_rate

        # ── Mood label derivation ──
        # Combine spectral features to classify mood
        bright = timbre.brightness
        noisy = timbre.noisiness
        warm = timbre.warmth
        dense = timbre.density

        if dense < 0.2 and self._smooth_energy < 0.15:
            timbre.mood_label = "ethereal"
        elif warm > 0.65 and bright < 0.4 and dense < 0.4:
            timbre.mood_label = "chill"
        elif noisy > 0.6 and dense > 0.6:
            timbre.mood_label = "aggressive"
        elif bright > 0.6 and dense > 0.5 and warm > 0.4:
            timbre.mood_label = "euphoric"
        elif bright > 0.55 and warm < 0.35:
            timbre.mood_label = "cold"
        elif dense > 0.5 and warm > 0.5:
            timbre.mood_label = "driving"
        elif bright < 0.35 and warm > 0.5:
            timbre.mood_label = "dark"
        elif dense < 0.35 and warm > 0.3:
            timbre.mood_label = "ambient"
        else:
            timbre.mood_label = "neutral"

        # Energy color (warm vs cool bias for color system)
        if warm > 0.6 and bright < 0.5:
            timbre.energy_color = "warm"
        elif warm < 0.35 and bright > 0.5:
            timbre.energy_color = "cool"
        else:
            timbre.energy_color = "neutral"

    # ══════════════════════════════════════════════════════════════════
    #  SECTION EVIDENCE (boosts for effects engine)
    # ══════════════════════════════════════════════════════════════════

    def _compute_section_evidence(self, energy: float, bass: float,
                                  mid: float, high: float, bpm: float,
                                  dt: float):
        """Compute section evidence from deep audio analysis.

        Uses CONTINUOUS signals from trajectory, rhythm, timbre, and events
        instead of binary if-chains. These are blended with MusicalIntelligence
        evidence in the effects engine for final section probabilities.
        """
        ev = self.state.section_evidence
        traj = self.state.trajectory
        rhythm = self.state.rhythm
        timbre = self.state.timbre

        # Reset
        for k in ev:
            ev[k] = 0.0

        # ── Breakdown evidence ──
        # Sparse rhythm, anticipation/falling trajectory, low energy, ethereal mood
        ev["breakdown"] = min(1.0, (
            0.30 * max(0.0, 1.0 - rhythm.groove_intensity / 0.3) +
            0.20 * (0.8 if traj.direction == "anticipation" else
                    0.5 if traj.direction == "falling" else 0.0) +
            0.25 * max(0.0, 1.0 - self._smooth_energy / 0.2) +
            0.15 * timbre.warmth * (1.0 - timbre.density) +
            0.10 * (1.0 - rhythm.hihat_density)
        ))

        # ── Buildup evidence ──
        # Rising trajectory, risers/noise present, hi-hat density increasing
        active_noise = any(e.event_type == "noise_build" and e.active for e in self._active_events)
        ev["buildup"] = min(1.0, (
            0.30 * (0.9 if traj.direction == "building" else
                    0.3 if traj.direction == "sustaining" and traj.momentum > 0.3 else 0.0) +
            0.25 * min(1.0, self._riser_accumulator * 2.0) +
            0.20 * (0.8 if active_noise else 0.0) +
            0.15 * rhythm.hihat_density * (0.8 if traj.direction == "building" else 0.3) +
            0.10 * min(1.0, traj.momentum * 2.0)
        ))

        # ── Drop evidence ──
        # Impacts/events, strong kick+bass+groove, character change, aggressive mood
        recent_impacts = [e for e in self._active_events
                         if e.event_type in ("impact", "drop_hit") and e.active]
        impact_score = max(e.intensity for e in recent_impacts) if recent_impacts else 0.0
        kick_bass_groove = (
            (1.0 if rhythm.kick_pattern == "four_on_floor" else 0.3) *
            min(1.0, bass / 0.4) *
            rhythm.groove_intensity
        )
        ev["drop"] = min(1.0, (
            0.30 * impact_score +
            0.25 * kick_bass_groove +
            0.20 * min(1.0, self._drop_character_signal * 2.0) +
            0.15 * (timbre.noisiness * self._smooth_energy) +
            0.10 * min(1.0, self._smooth_energy / 0.5)
        ))

        # ── Chorus evidence ──
        # Sustained high energy, melodic/euphoric mood, good groove, bright+warm
        sustain_high = (1.0 if traj.direction == "sustaining" else 0.3) * min(1.0, self._smooth_energy / 0.45)
        ev["chorus"] = min(1.0, (
            0.30 * sustain_high +
            0.25 * rhythm.groove_intensity * min(1.0, timbre.brightness) +
            0.20 * timbre.warmth * timbre.brightness +
            0.15 * rhythm.onset_regularity +
            0.10 * (1.0 - timbre.noisiness)  # tonal, not noisy
        ))

        # ── Verse evidence ──
        # Medium energy, stable, regular rhythm, neutral mood
        energy_mid = max(0.0, 1.0 - abs(self._smooth_energy - 0.35) * 3.0)
        ev["verse"] = min(1.0, (
            0.30 * (0.8 if traj.direction == "sustaining" else 0.2) * energy_mid +
            0.25 * rhythm.onset_regularity * max(0.0, 1.0 - rhythm.groove_intensity / 0.6) +
            0.20 * (1.0 - timbre.noisiness) +
            0.15 * timbre.warmth +
            0.10 * max(0.0, 1.0 - abs(timbre.brightness - 0.5) * 2.0)  # moderate brightness
        ))

    # ══════════════════════════════════════════════════════════════════
    #  MODULATION SIGNALS (direct lighting control)
    # ══════════════════════════════════════════════════════════════════

    def _update_modulation_signals(self, dt: float):
        """Compute direct modulation signals for lighting."""
        s = self.state

        # Riser intensity — drives lights upward, color brightening
        s.riser_intensity = self._riser_accumulator

        # Impact flash — triggers bump/flash responses
        recent_impacts = [e for e in self._active_events
                         if e.event_type in ("impact", "drop_hit") and e.active]
        if recent_impacts:
            s.impact_flash = max(e.intensity for e in recent_impacts)
        else:
            # Decay
            s.impact_flash *= max(0.0, 1.0 - dt * 8.0)

        # Sweep position — maps filter sweeps to color temperature
        active_sweep = next((e for e in self._active_events
                           if e.event_type.startswith("sweep") and e.active), None)
        if active_sweep:
            if active_sweep.event_type == "sweep_up":
                s.sweep_position += (1.0 - s.sweep_position) * min(1.0, dt * 4.0)
            else:
                s.sweep_position += (0.0 - s.sweep_position) * min(1.0, dt * 4.0)
        else:
            s.sweep_position += (0.5 - s.sweep_position) * min(1.0, dt * 1.0)

        # Anticipation level — "something is about to happen"
        if self.state.trajectory.direction == "anticipation":
            bars = self.state.trajectory.bars_in_direction
            s.anticipation_level = min(1.0, bars / 4.0)  # builds over 4 bars
        elif self.state.trajectory.direction == "building":
            s.anticipation_level = min(1.0, self._riser_accumulator + 0.3)
        else:
            s.anticipation_level *= max(0.0, 1.0 - dt * 2.0)

        # Drop character signal — exposed for effects engine drop detection
        s.drop_character_signal = self._drop_character_signal
        s.buildup_tracking_active = self._buildup_active

    # ══════════════════════════════════════════════════════════════════
    #  PUBLIC QUERY METHODS
    # ══════════════════════════════════════════════════════════════════

    def get_active_events(self) -> List[SoundEvent]:
        """Get currently active sound events."""
        return [ev for ev in self._active_events if ev.active]

    def has_active_event(self, event_type: str) -> bool:
        """Check if a specific event type is currently active."""
        return any(ev.event_type == event_type and ev.active for ev in self._active_events)

    def get_section_evidence(self) -> Dict[str, float]:
        """Get section evidence boosts for the effects engine."""
        return dict(self.state.section_evidence)

    def get_mood_label(self) -> str:
        """Get current timbral mood label."""
        return self.state.timbre.mood_label

    def get_trajectory(self) -> EnergyTrajectory:
        """Get current energy trajectory."""
        return self.state.trajectory
