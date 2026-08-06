"""
Musical Intelligence — Deep Instrument & Texture Understanding
==============================================================

Goes BEYOND AudioIntelligence's event/energy analysis to understand
WHAT is making the music — which element is carrying the energy,
how dense the mix is, how much ambiance/space is present, and
whether the groove is driving or floating.

SIX CONTINUOUS DIMENSIONS (all 0-1):

1. DOMINANT ELEMENT
   Which spectral region has the most CHANGE (not just energy).
   Outputs a continuous blend across element types:
   - bass_synth: low-frequency sustained tonal content
   - lead_synth: mid-high tonal with pitch movement
   - pad: sustained broadband, little change
   - drums: transient-heavy, regular onset pattern
   - vocal: mid-range with formant characteristics
   - noise: broadband non-tonal (risers, FX)

2. ELEMENT ACTIVITY (0-1)
   Is the dominant element getting busier or calmer?
   High = more onsets, filter modulation, pitch changes
   Low = sustained, static, repetitive

3. TEXTURE (0-1 per axis)
   - tonal_vs_noisy: 0=pure noise, 1=pure tone
   - percussive_vs_sustained: 0=all transients, 1=all sustain
   Combined into a texture label for look matching.

4. DENSITY (0-1)
   How many independent spectral layers are active simultaneously.
   0 = single element solo
   1 = full wall of sound, everything playing

5. AMBIANCE (0-1)
   How "wet" and spacious the mix sounds.
   Derived from spectral diffusion, decay characteristics, stereo spread.
   0 = tight, dry, in-your-face
   1 = washed out, reverby, spacious

6. DRIVE (0-1)
   How much the groove is pushing forward.
   Combines rhythmic regularity, kick strength, and energy momentum.
   0 = floating, no pulse
   1 = relentless four-on-floor with full energy

All outputs are continuous signals designed to feed the look library's
distance-based matching system. No hard rules — just musical fingerprints
that the look selector matches against look tags.
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
class DominantElement:
    """Which musical element is currently carrying the track."""
    bass_synth: float = 0.0    # 0-1 how much bass synth is dominant
    lead_synth: float = 0.0    # 0-1 how much lead synth is dominant
    pad: float = 0.0           # 0-1 how much pad/atmosphere is dominant
    drums: float = 0.0         # 0-1 how much drums are dominant
    vocal: float = 0.0         # 0-1 how much vocals are dominant
    noise: float = 0.0         # 0-1 how much noise/FX is dominant
    label: str = "unknown"     # the winning element name

    def dominant_label(self) -> str:
        """Return the element with highest score."""
        elements = {
            "bass_synth": self.bass_synth,
            "lead_synth": self.lead_synth,
            "pad": self.pad,
            "drums": self.drums,
            "vocal": self.vocal,
            "noise": self.noise,
        }
        winner = max(elements, key=elements.get)
        self.label = winner
        return winner

    def dominant_score(self) -> float:
        """How dominant is the leading element (0=equal mix, 1=solo)."""
        scores = [self.bass_synth, self.lead_synth, self.pad,
                  self.drums, self.vocal, self.noise]
        if not scores:
            return 0.0
        top = max(scores)
        total = sum(scores)
        if total < 0.01:
            return 0.0
        return top / total


@dataclass
class MusicalFingerprint:
    """Complete musical characterization of the current moment."""
    # Dimension 1: What element is carrying the track
    dominant: DominantElement = field(default_factory=DominantElement)

    # Dimension 2: How active/busy is the dominant element
    element_activity: float = 0.5   # 0=static/calm, 1=busy/intensifying

    # Dimension 3: Texture
    tonal_vs_noisy: float = 0.5     # 0=noisy, 1=tonal
    percussive_vs_sustained: float = 0.5  # 0=all transients, 1=all sustain
    texture_label: str = "neutral"  # derived: "tonal", "percussive", "noisy", "ambient", "driving"

    # Dimension 4: Density
    density: float = 0.5            # 0=sparse/solo, 1=full wall

    # Dimension 5: Ambiance
    ambiance: float = 0.5           # 0=dry/tight, 1=wet/spacious

    # Dimension 6: Drive
    drive: float = 0.5              # 0=floating, 1=relentless groove


# ══════════════════════════════════════════════════════════════════════
#  MUSICAL INTELLIGENCE ENGINE
# ══════════════════════════════════════════════════════════════════════

class MusicalIntelligence:
    """Derives deep musical understanding from spectral analysis.

    Sits alongside AudioIntelligence but focuses on WHAT is making
    the sound rather than WHAT is happening structurally.
    """

    def __init__(self):
        self.fingerprint = MusicalFingerprint()

        # ── Band-specific change tracking ──
        # We track the RATE OF CHANGE in each band, not just energy.
        # The band with the most change is "carrying" the track.
        self._history_len = 120  # ~2 seconds at 60fps
        self._bass_history: deque = deque(maxlen=self._history_len)
        self._mid_history: deque = deque(maxlen=self._history_len)
        self._high_history: deque = deque(maxlen=self._history_len)
        self._energy_history: deque = deque(maxlen=self._history_len)

        # ── Onset tracking per band (for element detection) ──
        self._bass_onset_acc: float = 0.0    # accumulated bass onsets
        self._mid_onset_acc: float = 0.0     # accumulated mid onsets
        self._high_onset_acc: float = 0.0    # accumulated high onsets
        self._prev_bass: float = 0.0
        self._prev_mid: float = 0.0
        self._prev_high: float = 0.0
        self._prev_energy: float = 0.0

        # ── Smoothed element scores ──
        self._smooth_bass_synth: float = 0.0
        self._smooth_lead_synth: float = 0.0
        self._smooth_pad: float = 0.0
        self._smooth_drums: float = 0.0
        self._smooth_vocal: float = 0.0
        self._smooth_noise: float = 0.0

        # ── Activity tracking ──
        self._activity_history: deque = deque(maxlen=60)  # ~1 second
        self._smooth_activity: float = 0.5

        # ── Density estimation ──
        self._band_active_count_smooth: float = 0.0

        # ── Ambiance estimation ──
        self._decay_estimator: float = 0.5     # tracks how fast energy decays
        self._spectral_spread: float = 0.5     # how evenly spread the spectrum is
        self._smooth_ambiance: float = 0.5

        # ── Drive estimation ──
        self._smooth_drive: float = 0.5
        self._onset_regularity_smooth: float = 0.5

        # ── Texture ──
        self._smooth_tonal: float = 0.5
        self._smooth_percussive: float = 0.5

        # ── Timing ──
        self._frame_count: int = 0
        self._last_update: float = 0.0

        # ── Onset timing for regularity analysis ──
        self._onset_times: deque = deque(maxlen=32)

    def update(self, energy: float, bass: float, mid: float, high: float,
               spectral_flux: float, is_beat: bool, bpm: float,
               dt: float = 0.016,
               audio_intel_state=None,
               vocal_active: bool = False) -> MusicalFingerprint:
        """Main update — call every frame.

        Args:
            energy, bass, mid, high: Band energies (0-1)
            spectral_flux: Rate of spectral change (0-1)
            is_beat: Beat detected this frame
            bpm: Current BPM
            dt: Delta time
            audio_intel_state: AudioIntelligenceState (if available)
            vocal_active: Whether vocal analyzer detects vocals

        Returns:
            MusicalFingerprint with all 6 dimensions
        """
        now = time.monotonic()
        self._frame_count += 1
        dt = max(0.001, min(0.1, dt))

        # Store history
        self._bass_history.append(bass)
        self._mid_history.append(mid)
        self._high_history.append(high)
        self._energy_history.append(energy)

        # ── Compute per-band deltas ──
        bass_delta = abs(bass - self._prev_bass)
        mid_delta = abs(mid - self._prev_mid)
        high_delta = abs(high - self._prev_high)
        energy_delta = abs(energy - self._prev_energy)

        # Accumulate onset energy per band (fast attack, slow decay)
        onset_decay = 3.0
        self._bass_onset_acc = max(
            self._bass_onset_acc * max(0.0, 1.0 - dt * onset_decay),
            bass_delta * 5.0
        )
        self._mid_onset_acc = max(
            self._mid_onset_acc * max(0.0, 1.0 - dt * onset_decay),
            mid_delta * 5.0
        )
        self._high_onset_acc = max(
            self._high_onset_acc * max(0.0, 1.0 - dt * onset_decay),
            high_delta * 5.0
        )

        # Track general onsets for regularity
        if energy_delta > 0.06 and energy > 0.1:
            if not self._onset_times or (now - self._onset_times[-1]) > 0.08:
                self._onset_times.append(now)

        # ── Run all dimension computations ──
        self._compute_dominant_element(
            energy, bass, mid, high, spectral_flux,
            bass_delta, mid_delta, high_delta,
            audio_intel_state, vocal_active, dt
        )
        self._compute_element_activity(
            energy, bass_delta, mid_delta, high_delta,
            spectral_flux, dt
        )
        self._compute_texture(
            energy, bass, mid, high, spectral_flux,
            audio_intel_state, dt
        )
        self._compute_density(energy, bass, mid, high, dt)
        self._compute_ambiance(
            energy, bass, mid, high, spectral_flux,
            audio_intel_state, dt
        )
        self._compute_drive(
            energy, bass, is_beat, bpm,
            audio_intel_state, dt
        )

        # Store for next frame
        self._prev_bass = bass
        self._prev_mid = mid
        self._prev_high = high
        self._prev_energy = energy
        self._last_update = now

        return self.fingerprint

    # ══════════════════════════════════════════════════════════════════
    #  DIMENSION 1: DOMINANT ELEMENT
    # ══════════════════════════════════════════════════════════════════

    def _compute_dominant_element(self, energy, bass, mid, high, flux,
                                  bass_delta, mid_delta, high_delta,
                                  ai_state, vocal_active, dt):
        """Determine which musical element is carrying the track.

        Uses both sustained energy AND rate of change to distinguish:
        - Bass synth: high bass, sustained, tonal (not just kicks)
        - Lead synth: high mids, tonal, with pitch movement
        - Pad: broadband sustained, very low change rate
        - Drums: transient-heavy, regular, mainly bass+high onsets
        - Vocal: mid-range with vocal analyzer confirmation
        - Noise: broadband, high flatness, not tonal
        """
        dom = self.fingerprint.dominant
        smooth = 4.0  # smoothing rate

        total_band = bass + mid + high + 0.001
        bass_ratio = bass / total_band
        mid_ratio = mid / total_band
        high_ratio = high / total_band

        # ── Compute raw element scores ──

        # Bass synth: high bass energy + sustained (low onset rate in bass)
        # Distinguished from kick drums by lower onset rate and higher sustain
        bass_sustain = bass * (1.0 - min(1.0, self._bass_onset_acc * 2.0))
        bass_synth_raw = (
            max(0.0, bass_ratio - 0.3) * 2.0 * bass +
            bass_sustain * 1.5
        )

        # Lead synth: mid-high energy, tonal, with activity (pitch changes)
        # Distinguished from pad by higher change rate
        mid_activity = self._mid_onset_acc
        lead_synth_raw = (
            max(0.0, mid_ratio - 0.25) * 2.0 * mid +
            mid_activity * 1.0 +
            max(0.0, mid - 0.3) * 0.5
        )
        # Reduce if very noisy (spectral flux too high = noise, not synth)
        if flux > 0.5:
            lead_synth_raw *= 0.5

        # Pad: broadband, sustained, very little change
        # All bands present but low activity
        band_balance = 1.0 - max(abs(bass_ratio - 0.33), abs(mid_ratio - 0.33), abs(high_ratio - 0.33)) * 3.0
        band_balance = max(0.0, band_balance)
        total_onset = self._bass_onset_acc + self._mid_onset_acc + self._high_onset_acc
        pad_raw = (
            band_balance * 1.5 *
            max(0.0, 1.0 - total_onset * 2.0) *
            max(0.0, energy - 0.05)
        )

        # Drums: high onset regularity, transient-heavy
        # Bass onsets (kicks) + high onsets (hats) with regularity
        drum_transients = (self._bass_onset_acc + self._high_onset_acc) * 0.5
        drum_raw = (
            drum_transients * 2.0 +
            self._onset_regularity_smooth * 0.5
        )
        # Reduce if too much sustained mid (that's a synth, not drums)
        if mid > 0.4 and self._mid_onset_acc < 0.1:
            drum_raw *= 0.5

        # Vocal: mid-range presence with vocal analyzer confirmation
        vocal_raw = 0.0
        if vocal_active:
            vocal_raw = mid * 1.5 + 0.3  # strong bias when vocal detected
        else:
            # Without vocal confirmation, only a hint from mid formant area
            vocal_raw = max(0.0, mid_ratio - 0.4) * mid * 0.3

        # Noise: broadband, high spectral flux, non-tonal
        noise_raw = 0.0
        if ai_state is not None:
            noise_raw = ai_state.timbre.noisiness * energy
            # Boost during active risers
            if any(e.event_type in ("riser", "noise_build") and e.active
                   for e in ai_state.events):
                noise_raw = max(noise_raw, 0.6)
        else:
            noise_raw = max(0.0, flux - 0.3) * 2.0

        # ── Smooth all element scores ──
        self._smooth_bass_synth += (bass_synth_raw - self._smooth_bass_synth) * min(1.0, dt * smooth)
        self._smooth_lead_synth += (lead_synth_raw - self._smooth_lead_synth) * min(1.0, dt * smooth)
        self._smooth_pad += (pad_raw - self._smooth_pad) * min(1.0, dt * smooth)
        self._smooth_drums += (drum_raw - self._smooth_drums) * min(1.0, dt * smooth)
        self._smooth_vocal += (vocal_raw - self._smooth_vocal) * min(1.0, dt * smooth)
        self._smooth_noise += (noise_raw - self._smooth_noise) * min(1.0, dt * smooth)

        # Normalize to 0-1 range
        scores = [self._smooth_bass_synth, self._smooth_lead_synth,
                  self._smooth_pad, self._smooth_drums,
                  self._smooth_vocal, self._smooth_noise]
        peak = max(max(scores), 0.01)

        dom.bass_synth = min(1.0, self._smooth_bass_synth / peak)
        dom.lead_synth = min(1.0, self._smooth_lead_synth / peak)
        dom.pad = min(1.0, self._smooth_pad / peak)
        dom.drums = min(1.0, self._smooth_drums / peak)
        dom.vocal = min(1.0, self._smooth_vocal / peak)
        dom.noise = min(1.0, self._smooth_noise / peak)
        dom.dominant_label()

    # ══════════════════════════════════════════════════════════════════
    #  DIMENSION 2: ELEMENT ACTIVITY
    # ══════════════════════════════════════════════════════════════════

    def _compute_element_activity(self, energy, bass_delta, mid_delta,
                                   high_delta, flux, dt):
        """How busy/active is the dominant element getting?

        Combines onset rate, spectral change, and short-term energy derivative.
        Rising activity = element picking up intensity.
        """
        # Combined change rate across all bands
        change_rate = bass_delta + mid_delta + high_delta + flux * 0.5
        self._activity_history.append(change_rate)

        # Activity = recent change rate vs historical average
        if len(self._activity_history) > 10:
            recent = sum(list(self._activity_history)[-10:]) / 10.0
            older = sum(list(self._activity_history)[:10]) / max(1, min(10, len(self._activity_history) - 10))
            # Activity increases when recent change exceeds historical
            raw_activity = min(1.0, recent * 5.0)
            # Activity DIRECTION: is it picking up or calming down?
            direction = 0.5 + (recent - older) * 5.0
            direction = max(0.0, min(1.0, direction))
            # Blend absolute activity with direction
            activity = raw_activity * 0.6 + direction * 0.4
        else:
            activity = min(1.0, change_rate * 5.0)

        self._smooth_activity += (activity - self._smooth_activity) * min(1.0, dt * 3.0)
        self.fingerprint.element_activity = self._smooth_activity

    # ══════════════════════════════════════════════════════════════════
    #  DIMENSION 3: TEXTURE
    # ══════════════════════════════════════════════════════════════════

    def _compute_texture(self, energy, bass, mid, high, flux,
                          ai_state, dt):
        """Texture: tonal vs noisy, percussive vs sustained.

        Tonal: clear pitch content, low spectral flatness
        Noisy: broadband, high flatness
        Percussive: sharp transients, high onset rate
        Sustained: smooth energy, low onset rate
        """
        # Tonal vs noisy
        if ai_state is not None:
            noisiness = ai_state.timbre.noisiness
        else:
            # Estimate: high flux + even band distribution = noisy
            total = bass + mid + high + 0.001
            evenness = 1.0 - max(abs(bass/total - 0.33), abs(mid/total - 0.33)) * 3.0
            noisiness = max(0.0, min(1.0, flux * 2.0 + evenness * 0.3))
        tonal = 1.0 - noisiness

        # Percussive vs sustained
        total_onset = self._bass_onset_acc + self._mid_onset_acc + self._high_onset_acc
        percussive = min(1.0, total_onset * 1.5)
        sustained = 1.0 - percussive

        self._smooth_tonal += (tonal - self._smooth_tonal) * min(1.0, dt * 3.0)
        self._smooth_percussive += (percussive - self._smooth_percussive) * min(1.0, dt * 3.0)

        fp = self.fingerprint
        fp.tonal_vs_noisy = self._smooth_tonal
        fp.percussive_vs_sustained = 1.0 - self._smooth_percussive  # 0=percussive, 1=sustained

        # Derive texture label
        if self._smooth_tonal > 0.6 and self._smooth_percussive < 0.4:
            fp.texture_label = "tonal"
        elif self._smooth_percussive > 0.6:
            fp.texture_label = "percussive"
        elif self._smooth_tonal < 0.4:
            fp.texture_label = "noisy"
        elif self._smooth_percussive < 0.3 and energy < 0.3:
            fp.texture_label = "ambient"
        elif self._smooth_percussive > 0.4 and self._smooth_tonal > 0.4:
            fp.texture_label = "driving"
        else:
            fp.texture_label = "neutral"

    # ══════════════════════════════════════════════════════════════════
    #  DIMENSION 4: DENSITY
    # ══════════════════════════════════════════════════════════════════

    def _compute_density(self, energy, bass, mid, high, dt):
        """How many independent spectral layers are active.

        Sparse: one band dominates, others near zero
        Full: all bands active at significant levels
        """
        # Count how many bands are above a meaningful threshold
        threshold = 0.1
        bands_active = 0
        if bass > threshold:
            bands_active += min(1.0, bass / 0.3)
        if mid > threshold:
            bands_active += min(1.0, mid / 0.3)
        if high > threshold:
            bands_active += min(1.0, high / 0.3)

        # Normalize to 0-1 (3 bands = fully dense)
        raw_density = bands_active / 3.0

        # Also factor in total energy — can't be "dense" at low volume
        energy_gate = min(1.0, energy / 0.2)
        raw_density *= energy_gate

        # Add onset diversity bonus (multiple bands with independent onsets = denser)
        onset_diversity = 0.0
        if self._bass_onset_acc > 0.05 and self._high_onset_acc > 0.05:
            onset_diversity += 0.1
        if self._mid_onset_acc > 0.05 and self._bass_onset_acc > 0.05:
            onset_diversity += 0.1
        raw_density = min(1.0, raw_density + onset_diversity)

        self._band_active_count_smooth += (raw_density - self._band_active_count_smooth) * min(1.0, dt * 3.0)
        self.fingerprint.density = self._band_active_count_smooth

    # ══════════════════════════════════════════════════════════════════
    #  DIMENSION 5: AMBIANCE
    # ══════════════════════════════════════════════════════════════════

    def _compute_ambiance(self, energy, bass, mid, high, flux, ai_state, dt):
        """How spacious/reverby the mix sounds.

        Tight/dry: sharp transients, fast energy decay, percussive
        Spacious/wet: slow decay, diffuse spectrum, low transient content

        We estimate this from:
        - Energy decay rate (how fast does energy fall after a transient?)
        - Spectral spread (how evenly distributed is energy across bands?)
        - Flux smoothness (reverby signals have smoother flux)
        """
        # Spectral spread: how evenly distributed across bands
        total = bass + mid + high + 0.001
        spread = 1.0 - (max(bass, mid, high) / total - 0.33) * 3.0
        spread = max(0.0, min(1.0, spread))

        # Energy decay estimate: compare current to recent peak
        if len(self._energy_history) > 10:
            recent_peak = max(list(self._energy_history)[-10:])
            if recent_peak > 0.1:
                decay_ratio = energy / recent_peak
                # High ratio = slow decay = more ambiance
                # Low ratio = fast decay = tight/dry
                decay_signal = decay_ratio
            else:
                decay_signal = 0.5
        else:
            decay_signal = 0.5

        # Flux smoothness: reverby content has lower spectral flux relative to energy
        flux_relative = flux / (energy + 0.01)
        flux_smoothness = max(0.0, 1.0 - flux_relative * 2.0)

        # Transient content: high transients = dry, low = wet
        transient_level = min(1.0, (self._bass_onset_acc + self._mid_onset_acc + self._high_onset_acc) * 0.7)
        non_transient = 1.0 - transient_level

        # Combined ambiance signal
        raw_ambiance = (
            spread * 0.2 +
            decay_signal * 0.3 +
            flux_smoothness * 0.2 +
            non_transient * 0.3
        )
        raw_ambiance = max(0.0, min(1.0, raw_ambiance))

        # Override from AI state if available
        if ai_state is not None:
            # Low brightness + low density = ambient feel
            ai_ambient_hint = max(0.0, (1.0 - ai_state.timbre.brightness) * 0.3 +
                                  (1.0 - ai_state.timbre.density) * 0.3)
            raw_ambiance = raw_ambiance * 0.7 + ai_ambient_hint * 0.3

        self._smooth_ambiance += (raw_ambiance - self._smooth_ambiance) * min(1.0, dt * 2.5)
        self.fingerprint.ambiance = self._smooth_ambiance

    # ══════════════════════════════════════════════════════════════════
    #  DIMENSION 6: DRIVE
    # ══════════════════════════════════════════════════════════════════

    def _compute_drive(self, energy, bass, is_beat, bpm, ai_state, dt):
        """How much the groove is pushing forward.

        Floating: no regular pulse, ambient, breakdown
        Driving: regular kick, strong bass, high energy, on-grid
        """
        now = time.monotonic()

        # Kick strength: bass onset regularity
        kick_contribution = 0.0
        if ai_state is not None:
            rhythm = ai_state.rhythm
            if rhythm.kick_pattern == "four_on_floor":
                kick_contribution = 0.8
            elif rhythm.kick_pattern == "half_time":
                kick_contribution = 0.4
            elif rhythm.kick_pattern == "breakbeat":
                kick_contribution = 0.6
            kick_contribution *= rhythm.groove_intensity
        else:
            # Estimate from bass onsets
            kick_contribution = min(1.0, self._bass_onset_acc * 3.0) * 0.5

        # Onset regularity: how "on-grid" are the onsets?
        regularity = 0.0
        recent_onsets = [t for t in self._onset_times if now - t < 4.0]
        if len(recent_onsets) >= 3:
            intervals = [recent_onsets[i+1] - recent_onsets[i]
                        for i in range(len(recent_onsets) - 1)]
            if intervals:
                mean_iv = sum(intervals) / len(intervals)
                if mean_iv > 0:
                    variance = sum((iv - mean_iv)**2 for iv in intervals) / len(intervals)
                    cv = math.sqrt(variance) / (mean_iv + 0.001)
                    regularity = max(0.0, min(1.0, 1.0 - cv * 2.0))

        self._onset_regularity_smooth += (regularity - self._onset_regularity_smooth) * min(1.0, dt * 2.0)

        # Energy momentum: is energy sustaining or growing?
        energy_momentum = 0.0
        if len(self._energy_history) >= 30:
            hist = list(self._energy_history)
            old_avg = sum(hist[-30:-15]) / 15.0
            new_avg = sum(hist[-15:]) / 15.0
            energy_momentum = max(0.0, min(1.0, 0.5 + (new_avg - old_avg) * 5.0))
        else:
            energy_momentum = min(1.0, energy)

        # Combined drive
        raw_drive = (
            kick_contribution * 0.35 +
            self._onset_regularity_smooth * 0.25 +
            min(1.0, energy * 1.2) * 0.2 +
            energy_momentum * 0.2
        )
        raw_drive = max(0.0, min(1.0, raw_drive))

        self._smooth_drive += (raw_drive - self._smooth_drive) * min(1.0, dt * 3.0)
        self.fingerprint.drive = self._smooth_drive
