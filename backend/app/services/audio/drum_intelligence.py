"""
Drum Intelligence — The Backbone of EDM Understanding
======================================================

Drums carry everything in electronic music. They tell you:
- Song structure: kick absence = breakdown, kick return = drop,
  snare rolls = buildup, full kit = verse/chorus/drop
- Energy level: hi-hat density, kick intensity, overall drum power
- Groove feel: straight vs swing, tight vs loose, human vs machine
- Transition cues: fills, rolls, drops, one-shot impacts
- Strobe/chase timing: lock to kick/snare/hi-hat patterns

ANALYSIS DIMENSIONS (all continuous 0-1):

1. KICK CONFIDENCE (0-1)
   Not just "is there a kick" but HOW STRONG the kick pattern is.
   Distinguishes four-on-floor from half-time, breakbeat, and absence.
   Tracks regularity (machine-tight vs human-loose) and power.

2. SNARE PRESENCE (0-1)
   Detects mid-frequency transients with snare characteristics.
   High = strong snare on 2&4 or rolls; Low = no snare detected.
   Snare rolls are a KEY buildup indicator.

3. HI-HAT CHARACTER (0-1 per axis)
   - density: sparse (breakdown) → dense (buildup/drop)
   - openness: closed (tight) → open (washy, breathing)
   Hi-hat acceleration (density increasing) = buildup signal.

4. DRUM POWER (0-1)
   Overall drum contribution to the mix. High = drums dominating,
   Low = melodic/ambient section with minimal percussion.
   THE most important section indicator — drum absence = breakdown.

5. GROOVE TIGHTNESS (0-1)
   How quantized/machine-like the rhythm is.
   0 = loose/human/swung, 1 = machine-tight grid lock.
   Tight = drop/chorus energy. Loose = verse/breakdown feel.

6. FILL DETECTOR (0-1)
   Detects drum fills and rolls (transition indicators).
   Triggered by rapid onset density spike in multiple bands.
   Decays quickly — it's a moment, not a state.

7. KICK RETURN SIGNAL (0-1)
   Fires when kick returns after absence. This IS the drop signal
   more than anything else in EDM. Decays over ~2 seconds.

OUTPUTS DESIGNED TO FEED:
- Section detection (MusicalIntelligence + effects engine)
- Strobe timing (lock to kick hits when drum_power > 0.6)
- Chase speed (scales with hi-hat density)
- Look selection (drum tags: "four_on_floor", "half_time", "no_drums", etc.)
- Movement accents (kick = downward accent, snare = flash/bump)
"""

import math
import time
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class DrumState:
    """Complete drum analysis output — updated every frame."""

    # ── Core dimensions ──
    kick_confidence: float = 0.0      # 0=no kick, 1=strong regular kick pattern
    kick_intensity: float = 0.0       # instantaneous kick strength (for accents)
    snare_presence: float = 0.0       # 0=no snare, 1=strong snare pattern
    snare_intensity: float = 0.0      # instantaneous snare hit strength

    # ── Hi-hat ──
    hihat_density: float = 0.0        # 0=sparse, 1=dense (16th notes)
    hihat_openness: float = 0.5       # 0=closed/tight, 1=open/washy
    hihat_acceleration: float = 0.0   # positive = getting denser (buildup signal)

    # ── Overall ──
    drum_power: float = 0.0           # 0=no drums, 1=full kit dominating
    groove_tightness: float = 0.5     # 0=loose/human, 1=machine-tight
    drum_energy: float = 0.0          # combined drum energy (for dimmer scaling)

    # ── Transition signals ──
    fill_intensity: float = 0.0       # 0=normal, 1=drum fill happening now
    kick_return: float = 0.0          # fires when kick comes back after absence
    snare_roll: float = 0.0           # detects snare/clap rolls (buildup indicator)

    # ── Pattern classification ──
    kick_pattern: str = "none"        # "none", "sparse", "half_time", "four_on_floor", "double_time"
    groove_label: str = "none"        # "none", "minimal", "driving", "pounding", "rolling"

    # ── Timing outputs for strobe/chase ──
    kick_phase: float = 0.0           # 0-1 phase within kick cycle (for strobe sync)
    snare_phase: float = 0.0          # 0-1 phase within snare cycle
    suggested_strobe_rate: float = 0.0  # Hz: suggested strobe rate based on groove
    suggested_chase_speed: float = 1.0  # multiplier: chase speed based on hihat

    # ── Section hints (what drums alone tell us about structure) ──
    drums_say_breakdown: float = 0.0  # evidence for breakdown from drums alone
    drums_say_buildup: float = 0.0    # evidence for buildup from drums alone
    drums_say_drop: float = 0.0       # evidence for drop from drums alone
    drums_say_verse: float = 0.0      # evidence for verse/chorus from drums alone


# ══════════════════════════════════════════════════════════════════════
#  DRUM INTELLIGENCE ENGINE
# ══════════════════════════════════════════════════════════════════════

class DrumIntelligence:
    """Deep drum pattern analysis for EDM lighting.

    Call update() every audio frame (~60fps). Receives the same band
    energies as MusicalIntelligence and produces a DrumState with all
    drum dimensions.
    """

    def __init__(self):
        self.state = DrumState()

        # ── Kick detection ──
        self._kick_onset_times: deque = deque(maxlen=64)
        self._kick_onset_strengths: deque = deque(maxlen=64)
        self._prev_bass: float = 0.0
        self._smooth_kick_rate: float = 0.0
        self._smooth_kick_intensity: float = 0.0
        self._smooth_kick_confidence: float = 0.0
        self._kick_absent_frames: int = 0
        self._kick_was_absent: bool = False  # tracks if kick was recently absent
        self._kick_absent_threshold: int = 90  # ~1.5s at 60fps before "absent"
        self._kick_return_decay: float = 0.0

        # ── Snare detection ──
        # Snare lives in mid band — transient-heavy, not sustained
        self._snare_onset_times: deque = deque(maxlen=64)
        self._prev_mid: float = 0.0
        self._prev_mid_delta: float = 0.0
        self._smooth_snare_rate: float = 0.0
        self._smooth_snare_presence: float = 0.0
        self._smooth_snare_intensity: float = 0.0
        self._snare_roll_detector: float = 0.0  # accumulates rapid snare hits

        # ── Hi-hat detection ──
        self._hihat_onset_times: deque = deque(maxlen=64)
        self._prev_high: float = 0.0
        self._smooth_hihat_density: float = 0.0
        self._prev_hihat_density: float = 0.0  # for acceleration tracking
        self._smooth_hihat_openness: float = 0.5

        # ── Overall drum tracking ──
        self._transient_accumulator: float = 0.0  # total transient energy
        self._sustained_accumulator: float = 0.0  # total sustained energy
        self._smooth_drum_power: float = 0.0
        self._smooth_drum_energy: float = 0.0

        # ── Groove analysis ──
        self._kick_intervals: deque = deque(maxlen=32)
        self._smooth_tightness: float = 0.5

        # ── Fill detection ──
        self._onset_burst_accumulator: float = 0.0
        self._smooth_fill: float = 0.0

        # ── Phase tracking ──
        self._last_kick_time: float = 0.0
        self._last_snare_time: float = 0.0
        self._kick_period_estimate: float = 0.5  # seconds between kicks

        # ── History for trend detection ──
        self._hihat_density_history: deque = deque(maxlen=120)  # 2s
        self._drum_power_history: deque = deque(maxlen=120)
        self._kick_confidence_history: deque = deque(maxlen=120)

        self._frame_count: int = 0

    def update(self, bass: float, mid: float, high: float,
               energy: float, spectral_flux: float,
               is_beat: bool, bpm: float,
               dt: float = 0.016) -> DrumState:
        """Main update — call every audio frame.

        Args:
            bass: Low frequency energy (0-1), contains kick
            mid: Mid frequency energy (0-1), contains snare
            high: High frequency energy (0-1), contains hi-hats
            energy: Overall energy (0-1)
            spectral_flux: Rate of spectral change (0-1)
            is_beat: Beat detected this frame
            bpm: Current tempo
            dt: Delta time in seconds

        Returns:
            DrumState with all dimensions updated
        """
        now = time.monotonic()
        self._frame_count += 1
        dt = max(0.001, min(0.1, dt))
        bpm = max(60.0, min(200.0, bpm))
        beats_per_sec = bpm / 60.0

        # ── Detect onsets in each band ──
        self._detect_kick(bass, energy, now, dt, bpm)
        self._detect_snare(mid, bass, high, now, dt, bpm)
        self._detect_hihat(high, mid, now, dt, bpm)

        # ── Compute all dimensions ──
        self._compute_drum_power(bass, mid, high, energy, spectral_flux, dt)
        self._compute_groove(bpm, now, dt)
        self._compute_fill(spectral_flux, dt)
        self._compute_kick_return(now, dt)
        self._compute_phases(now, bpm)
        self._compute_section_hints(bpm, dt)
        self._compute_timing_suggestions(bpm)

        # ── Update histories ──
        self._hihat_density_history.append(self.state.hihat_density)
        self._drum_power_history.append(self.state.drum_power)
        self._kick_confidence_history.append(self.state.kick_confidence)

        # Store for next frame
        self._prev_bass = bass
        self._prev_mid = mid
        self._prev_high = high

        return self.state

    # ══════════════════════════════════════════════════════════════════
    #  KICK DETECTION
    # ══════════════════════════════════════════════════════════════════

    def _detect_kick(self, bass: float, energy: float,
                     now: float, dt: float, bpm: float):
        """Detect kick drum hits from bass band transients.

        Kick = sharp positive bass delta + sufficient bass energy.
        Distinguished from bass synth by transient sharpness.
        """
        s = self.state
        bass_delta = bass - self._prev_bass

        # Kick onset: positive bass jump above threshold
        # Higher threshold than general onset — we want actual kicks, not bass wobble
        kick_threshold = 0.03  # tuned for EDM kick detection
        min_interval = 0.12   # max ~8 kicks/sec (faster than any reasonable tempo)

        is_kick = (
            bass_delta > kick_threshold and
            bass > 0.08 and
            (not self._kick_onset_times or (now - self._kick_onset_times[-1]) > min_interval)
        )

        if is_kick:
            self._kick_onset_times.append(now)
            self._kick_onset_strengths.append(bass_delta)
            self._last_kick_time = now

            # Track kick interval for period estimation
            if len(self._kick_onset_times) >= 2:
                interval = self._kick_onset_times[-1] - self._kick_onset_times[-2]
                if 0.15 < interval < 2.0:  # reasonable kick interval
                    self._kick_intervals.append(interval)

        # ── Kick rate (smoothed) ──
        window = 4.0
        recent_kicks = [t for t in self._kick_onset_times if now - t < window]
        kick_rate = len(recent_kicks) / window
        self._smooth_kick_rate += (kick_rate - self._smooth_kick_rate) * min(1.0, dt * 3.0)

        # ── Kick intensity (instantaneous — fast attack, moderate decay) ──
        if is_kick:
            self._smooth_kick_intensity = max(self._smooth_kick_intensity, bass_delta * 8.0)
        self._smooth_kick_intensity *= max(0.0, 1.0 - dt * 10.0)  # fast decay
        s.kick_intensity = min(1.0, self._smooth_kick_intensity)

        # ── Kick confidence: combines rate + regularity + strength ──
        expected_4otf = bpm / 60.0  # expected kicks/sec for four-on-floor

        # Rate score: how close to expected four-on-floor rate
        rate_score = 0.0
        if expected_4otf > 0:
            rate_ratio = self._smooth_kick_rate / expected_4otf
            rate_score = max(0.0, 1.0 - abs(rate_ratio - 1.0) * 1.5)

        # Strength score: average kick strength
        recent_strengths = [s for s in self._kick_onset_strengths
                           if len(self._kick_onset_times) > 0]
        avg_strength = 0.0
        if recent_strengths:
            avg_strength = min(1.0, sum(recent_strengths[-8:]) / max(1, len(recent_strengths[-8:])) * 10.0)

        # Combined confidence
        raw_confidence = 0.5 * rate_score + 0.3 * avg_strength + 0.2 * self.state.groove_tightness
        self._smooth_kick_confidence += (raw_confidence - self._smooth_kick_confidence) * min(1.0, dt * 2.0)
        s.kick_confidence = min(1.0, max(0.0, self._smooth_kick_confidence))

        # ── Kick pattern classification ──
        if self._smooth_kick_rate < 0.3:
            s.kick_pattern = "none"
            self._kick_absent_frames += 1
        elif self._smooth_kick_rate < expected_4otf * 0.55:
            s.kick_pattern = "sparse"
            self._kick_absent_frames = 0
        elif self._smooth_kick_rate < expected_4otf * 0.75:
            s.kick_pattern = "half_time"
            self._kick_absent_frames = 0
        elif self._smooth_kick_rate < expected_4otf * 1.3:
            s.kick_pattern = "four_on_floor"
            self._kick_absent_frames = 0
        else:
            s.kick_pattern = "double_time"
            self._kick_absent_frames = 0

        # Track absence for kick return detection
        if self._kick_absent_frames > self._kick_absent_threshold:
            self._kick_was_absent = True

    # ══════════════════════════════════════════════════════════════════
    #  SNARE DETECTION
    # ══════════════════════════════════════════════════════════════════

    def _detect_snare(self, mid: float, bass: float, high: float,
                      now: float, dt: float, bpm: float):
        """Detect snare/clap hits from mid band transients.

        Snare = sharp mid transient, often with some high splash.
        Distinguished from synth stabs by the transient shape.
        """
        s = self.state
        mid_delta = mid - self._prev_mid

        # Snare onset: positive mid jump + some high energy (snare has splash)
        # Exclude bass-only transients (those are kicks)
        bass_delta = bass - self._prev_bass
        is_snare = (
            mid_delta > 0.025 and
            mid > 0.06 and
            mid_delta > bass_delta * 0.5 and  # not just bleed from kick
            (not self._snare_onset_times or (now - self._snare_onset_times[-1]) > 0.10)
        )

        if is_snare:
            self._snare_onset_times.append(now)
            self._last_snare_time = now

        # ── Snare rate ──
        window = 4.0
        recent_snares = [t for t in self._snare_onset_times if now - t < window]
        snare_rate = len(recent_snares) / window
        self._smooth_snare_rate += (snare_rate - self._smooth_snare_rate) * min(1.0, dt * 3.0)

        # ── Snare intensity (instantaneous) ──
        if is_snare:
            self._smooth_snare_intensity = max(self._smooth_snare_intensity, mid_delta * 8.0)
        self._smooth_snare_intensity *= max(0.0, 1.0 - dt * 10.0)
        s.snare_intensity = min(1.0, self._smooth_snare_intensity)

        # ── Snare presence (smoothed, 0-1) ──
        expected_snare = bpm / 120.0  # snare on 2 and 4 = half the beat rate
        if expected_snare > 0:
            snare_ratio = self._smooth_snare_rate / expected_snare
            raw_presence = min(1.0, snare_ratio)
        else:
            raw_presence = 0.0
        self._smooth_snare_presence += (raw_presence - self._smooth_snare_presence) * min(1.0, dt * 2.0)
        s.snare_presence = min(1.0, max(0.0, self._smooth_snare_presence))

        # ── Snare roll detection ──
        # Snare rolls: rapid snare hits (>4/sec) sustained over time
        # Key buildup indicator in EDM
        if snare_rate > 4.0:
            self._snare_roll_detector += dt * min(1.0, (snare_rate - 4.0) / 4.0)
        else:
            self._snare_roll_detector *= max(0.0, 1.0 - dt * 3.0)
        s.snare_roll = min(1.0, self._snare_roll_detector)

        self._prev_mid_delta = mid_delta

    # ══════════════════════════════════════════════════════════════════
    #  HI-HAT DETECTION
    # ══════════════════════════════════════════════════════════════════

    def _detect_hihat(self, high: float, mid: float,
                      now: float, dt: float, bpm: float):
        """Detect hi-hat patterns from high frequency transients.

        Tracks density (how many hats/sec) and openness (sustained vs sharp).
        Hi-hat acceleration (density increasing) is a key buildup signal.
        """
        s = self.state
        high_delta = high - self._prev_high

        # Hi-hat onset: positive high jump
        is_hihat = (
            high_delta > 0.02 and
            high > 0.04 and
            (not self._hihat_onset_times or (now - self._hihat_onset_times[-1]) > 0.05)
        )

        if is_hihat:
            self._hihat_onset_times.append(now)

        # ── Hi-hat density ──
        window = 3.0
        recent_hats = [t for t in self._hihat_onset_times if now - t < window]
        hat_rate = len(recent_hats) / window

        # Normalize: 0 hats/s = 0, ~8+ = 1.0 (16th notes at 120bpm = 8/sec)
        raw_density = min(1.0, hat_rate / 8.0)
        self._smooth_hihat_density += (raw_density - self._smooth_hihat_density) * min(1.0, dt * 3.0)
        s.hihat_density = self._smooth_hihat_density

        # ── Hi-hat acceleration (buildup detector) ──
        # Compare recent density to density 1 second ago
        if len(self._hihat_density_history) > 60:
            old_density = sum(list(self._hihat_density_history)[-60:-30]) / 30.0
            new_density = sum(list(self._hihat_density_history)[-30:]) / 30.0
            s.hihat_acceleration = max(-1.0, min(1.0, (new_density - old_density) * 5.0))
        else:
            s.hihat_acceleration = 0.0

        # ── Hi-hat openness ──
        # Open hi-hats: sustained high-frequency energy (less transient, more decay)
        # Closed hi-hats: sharp transient, fast decay
        if high > 0.03:
            # If high energy sustains relative to delta, it's more "open"
            sustain_ratio = high / (abs(high_delta) + high + 0.001)
            raw_openness = min(1.0, sustain_ratio * 1.5)
        else:
            raw_openness = 0.5  # neutral when no signal
        self._smooth_hihat_openness += (raw_openness - self._smooth_hihat_openness) * min(1.0, dt * 2.0)
        s.hihat_openness = self._smooth_hihat_openness

        self._prev_hihat_density = self._smooth_hihat_density

    # ══════════════════════════════════════════════════════════════════
    #  DRUM POWER (overall percussion contribution)
    # ══════════════════════════════════════════════════════════════════

    def _compute_drum_power(self, bass: float, mid: float, high: float,
                            energy: float, spectral_flux: float, dt: float):
        """How much drums are contributing to the mix vs melodic content.

        High drum power = percussion-dominated (drop, heavy verse).
        Low drum power = melodic/ambient section (breakdown, pad section).

        Key insight: drums are TRANSIENT-heavy. If most energy comes from
        transients (high onset rate, fast attack/decay), drums are dominant.
        If energy is sustained (slow changes), melodic content dominates.
        """
        s = self.state

        # Transient score: how much of the energy comes from sharp changes
        bass_delta = abs(bass - self._prev_bass)
        mid_delta = abs(mid - self._prev_mid)
        high_delta = abs(high - self._prev_high)

        total_delta = bass_delta + mid_delta + high_delta
        total_energy = bass + mid + high + 0.001

        # Transient ratio: what fraction of energy is "changing"
        transient_ratio = min(1.0, total_delta / (total_energy * 0.3 + 0.001))

        # Track transient vs sustained accumulation
        self._transient_accumulator += (transient_ratio - self._transient_accumulator) * min(1.0, dt * 4.0)
        self._sustained_accumulator += ((1.0 - transient_ratio) - self._sustained_accumulator) * min(1.0, dt * 4.0)

        # Drum power = kick confidence + snare presence + hihat density + transient ratio
        # Weighted toward kick (most important) and overall transient nature
        raw_power = (
            0.35 * s.kick_confidence +
            0.20 * s.snare_presence +
            0.15 * s.hihat_density +
            0.20 * self._transient_accumulator +
            0.10 * min(1.0, spectral_flux * 2.0)  # spectral change = percussive
        )
        self._smooth_drum_power += (raw_power - self._smooth_drum_power) * min(1.0, dt * 2.5)
        s.drum_power = min(1.0, max(0.0, self._smooth_drum_power))

        # Drum energy: instantaneous energy that's drum-related
        drum_e = (
            0.40 * s.kick_intensity +
            0.25 * s.snare_intensity +
            0.20 * s.hihat_density * high +
            0.15 * self._transient_accumulator * energy
        )
        self._smooth_drum_energy += (drum_e - self._smooth_drum_energy) * min(1.0, dt * 6.0)
        s.drum_energy = min(1.0, max(0.0, self._smooth_drum_energy))

    # ══════════════════════════════════════════════════════════════════
    #  GROOVE ANALYSIS
    # ══════════════════════════════════════════════════════════════════

    def _compute_groove(self, bpm: float, now: float, dt: float):
        """Analyze groove tightness and classify the overall pattern."""
        s = self.state

        # ── Groove tightness from kick interval regularity ──
        if len(self._kick_intervals) >= 4:
            intervals = list(self._kick_intervals)[-16:]
            mean_iv = sum(intervals) / len(intervals)
            if mean_iv > 0:
                variance = sum((iv - mean_iv)**2 for iv in intervals) / len(intervals)
                cv = math.sqrt(variance) / (mean_iv + 0.001)
                # Low CV = tight/quantized, high CV = loose/human
                raw_tightness = max(0.0, min(1.0, 1.0 - cv * 3.0))
            else:
                raw_tightness = 0.5
        else:
            raw_tightness = 0.3  # default to slightly loose when unknown
        self._smooth_tightness += (raw_tightness - self._smooth_tightness) * min(1.0, dt * 1.5)
        s.groove_tightness = self._smooth_tightness

        # ── Groove label ──
        power = s.drum_power
        kick = s.kick_confidence
        if power < 0.15:
            s.groove_label = "none"
        elif power < 0.3:
            s.groove_label = "minimal"
        elif kick > 0.6 and s.groove_tightness > 0.6:
            if s.hihat_density > 0.5:
                s.groove_label = "pounding"
            else:
                s.groove_label = "driving"
        elif s.snare_roll > 0.3:
            s.groove_label = "rolling"
        else:
            s.groove_label = "driving"

    # ══════════════════════════════════════════════════════════════════
    #  FILL DETECTION
    # ══════════════════════════════════════════════════════════════════

    def _compute_fill(self, spectral_flux: float, dt: float):
        """Detect drum fills (rapid multi-band onset bursts).

        Fills are transition indicators — rapid percussion changes across
        multiple frequency bands that break the normal pattern.
        """
        s = self.state

        # A fill is a sudden burst of onset activity above normal
        # Use spectral flux as proxy for multi-band percussion change
        normal_flux = 0.05
        burst = max(0.0, spectral_flux - normal_flux) * 5.0

        # Accumulate bursts (fills last a few beats, not single frames)
        if burst > 0.3:
            self._onset_burst_accumulator += burst * dt * 3.0
        else:
            self._onset_burst_accumulator *= max(0.0, 1.0 - dt * 4.0)

        self._onset_burst_accumulator = min(1.0, self._onset_burst_accumulator)
        self._smooth_fill += (self._onset_burst_accumulator - self._smooth_fill) * min(1.0, dt * 6.0)
        s.fill_intensity = min(1.0, max(0.0, self._smooth_fill))

    # ══════════════════════════════════════════════════════════════════
    #  KICK RETURN DETECTION (the drop signal)
    # ══════════════════════════════════════════════════════════════════

    def _compute_kick_return(self, now: float, dt: float):
        """Detect when kick returns after absence — THE key drop signal.

        In EDM: breakdown = no kick. Drop = kick comes back hard.
        This transition is the single most reliable drop indicator.
        """
        s = self.state

        # Did the kick just come back?
        if self._kick_was_absent and s.kick_pattern != "none":
            # Kick has returned after being absent!
            self._kick_return_decay = min(1.0, s.kick_intensity + 0.5)
            self._kick_was_absent = False
            logger.info(f"DRUM_INTEL: Kick return detected! intensity={s.kick_intensity:.3f}")

        # Decay the return signal over ~2 seconds
        self._kick_return_decay *= max(0.0, 1.0 - dt * 1.5)
        s.kick_return = self._kick_return_decay

    # ══════════════════════════════════════════════════════════════════
    #  PHASE TRACKING (for strobe/chase sync)
    # ══════════════════════════════════════════════════════════════════

    def _compute_phases(self, now: float, bpm: float):
        """Track kick and snare phase for strobe/chase synchronization."""
        s = self.state

        # Kick period estimation
        if len(self._kick_intervals) >= 2:
            recent = list(self._kick_intervals)[-8:]
            self._kick_period_estimate = sum(recent) / len(recent)
        else:
            self._kick_period_estimate = 60.0 / bpm  # fallback: one kick per beat

        # Kick phase: 0→1 cycle between kicks
        time_since_kick = now - self._last_kick_time
        if self._kick_period_estimate > 0:
            s.kick_phase = min(1.0, time_since_kick / self._kick_period_estimate)
        else:
            s.kick_phase = 0.0

        # Snare phase: 0→1 cycle between snares
        time_since_snare = now - self._last_snare_time
        snare_period = 120.0 / bpm  # snare every 2 beats
        if snare_period > 0:
            s.snare_phase = min(1.0, time_since_snare / snare_period)
        else:
            s.snare_phase = 0.0

    # ══════════════════════════════════════════════════════════════════
    #  TIMING SUGGESTIONS (for effects engine)
    # ══════════════════════════════════════════════════════════════════

    def _compute_timing_suggestions(self, bpm: float):
        """Suggest strobe rate and chase speed based on drum analysis."""
        s = self.state

        # ── Strobe rate suggestion ──
        # Lock to kick when kick is strong, otherwise to beat
        if s.kick_confidence > 0.5 and s.kick_pattern == "four_on_floor":
            # Strobe on every kick (quarter notes)
            s.suggested_strobe_rate = bpm / 60.0
        elif s.kick_confidence > 0.3:
            # Strobe on every other kick (half notes)
            s.suggested_strobe_rate = bpm / 120.0
        elif s.snare_roll > 0.3:
            # During snare roll: faster strobe
            s.suggested_strobe_rate = min(3.0, bpm / 30.0)
        else:
            s.suggested_strobe_rate = 0.0  # no strobe suggested

        # ── Chase speed suggestion ──
        # Hi-hat density directly maps to chase subdivision
        # Sparse hats = slow chase (whole notes), dense hats = fast chase (8th/16th)
        if s.hihat_density < 0.1:
            s.suggested_chase_speed = 0.25  # very slow (whole notes)
        elif s.hihat_density < 0.3:
            s.suggested_chase_speed = 0.5   # half notes
        elif s.hihat_density < 0.5:
            s.suggested_chase_speed = 1.0   # quarter notes
        elif s.hihat_density < 0.7:
            s.suggested_chase_speed = 2.0   # eighth notes
        else:
            s.suggested_chase_speed = 4.0   # sixteenth notes

    # ══════════════════════════════════════════════════════════════════
    #  SECTION HINTS (what drums alone say about structure)
    # ══════════════════════════════════════════════════════════════════

    def _compute_section_hints(self, bpm: float, dt: float):
        """Derive section evidence from drum patterns alone.

        These hints get blended into the main section evidence in the
        effects engine. Drums are THE strongest structure signal in EDM.
        """
        s = self.state

        # ── BREAKDOWN: no drums, no kick, maybe just hi-hat shimmer ──
        s.drums_say_breakdown = (
            0.40 * max(0.0, 1.0 - s.drum_power / 0.2) +    # low drum power
            0.30 * max(0.0, 1.0 - s.kick_confidence / 0.15) +  # no kick
            0.20 * max(0.0, 1.0 - s.snare_presence / 0.1) +   # no snare
            0.10 * s.hihat_openness                             # open/washy hats (if any)
        )
        s.drums_say_breakdown = min(1.0, max(0.0, s.drums_say_breakdown))

        # ── BUILDUP: snare roll, hihat acceleration, increasing density ──
        s.drums_say_buildup = (
            0.35 * s.snare_roll +                              # snare/clap roll
            0.25 * max(0.0, s.hihat_acceleration) +            # hats getting denser
            0.20 * s.fill_intensity +                          # drum fill happening
            0.10 * min(1.0, s.hihat_density * 1.5) +           # dense hats
            0.10 * max(0.0, 1.0 - s.kick_confidence / 0.5)    # kick often drops out during buildup
        )
        s.drums_say_buildup = min(1.0, max(0.0, s.drums_say_buildup))

        # ── DROP: kick return, full kit, four-on-floor, maximum power ──
        four_otf = 1.0 if s.kick_pattern == "four_on_floor" else 0.0
        s.drums_say_drop = (
            0.30 * s.kick_return +                             # THE drop signal
            0.25 * s.kick_confidence +                         # strong kick
            0.20 * four_otf +                                  # four on the floor
            0.15 * s.drum_power +                              # full kit
            0.10 * s.groove_tightness                          # machine-tight
        )
        s.drums_say_drop = min(1.0, max(0.0, s.drums_say_drop))

        # ── VERSE/CHORUS: steady drums, moderate power, regular pattern ──
        s.drums_say_verse = (
            0.30 * s.kick_confidence * (1.0 - s.kick_return) +  # steady kick (not just returned)
            0.25 * max(0.0, 1.0 - abs(s.drum_power - 0.5) * 3.0) +  # moderate power
            0.25 * s.groove_tightness +                         # regular groove
            0.20 * s.snare_presence * (1.0 - s.snare_roll)     # snare on 2&4 (not rolling)
        )
        s.drums_say_verse = min(1.0, max(0.0, s.drums_say_verse))
