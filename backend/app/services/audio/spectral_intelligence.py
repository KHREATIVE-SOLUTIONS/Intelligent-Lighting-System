"""
Spectral Intelligence — Understanding WHAT Is Playing
======================================================

The missing link between raw frequency bands and musical understanding.
DrumIntelligence knows about rhythm, MusicalIntelligence knows about mood,
but neither can tell the difference between a screaming supersaw lead and
a reverb pad when both live in the same frequency range at the same energy.

This service answers: "what KIND of sound is happening right now?"

ANALYSIS DIMENSIONS (all continuous 0-1):

1. SPECTRAL SHAPE
   - brightness: spectral centroid normalized (dark bass → bright leads)
   - spread: how wide the spectrum is (narrow lead vs full wall)
   - flatness: noise-like (1.0) vs tonal (0.0)
   - tilt: energy distribution — top-heavy vs bottom-heavy

2. ONSET TEXTURE (per-frame, tracks attack/decay character)
   - attack_sharpness: how fast energy rises (0=soft pad, 1=hard pluck/hit)
   - sustain_level: how much energy persists after onset (0=staccato, 1=sustained)
   - transient_density: how many onsets per second (sparse vs busy)
   These distinguish: drums (sharp+short), pads (soft+sustained),
   pluck synths (sharp+short), supersaw (soft+sustained+bright)

3. HARMONIC CONTENT
   - tonality: how pitched/harmonic the signal is (0=noise, 1=pure tone)
   - harmonic_complexity: simple sine vs rich harmonics (saw/square)
   - pitch_stability: stable note vs sweeping/rising pitch
   These distinguish: risers (low stability), leads (high tonality+stability),
   noise builds (low tonality), bass drops (high tonality+low brightness)

4. MOMENT CHARACTER (derived composite labels)
   - melodic_intensity: how much "musical content" is happening (vs silence/drums)
   - wall_of_sound: full-spectrum saturation (the drop wall)
   - ethereal: spacious, high, soft, tonal (breakdown pads)
   - aggressive: bright, harsh, loud, noisy (drop leads)
   - rising: pitch/energy/density increasing (buildups)

DESIGN PRINCIPLES:
  - All computation from 7 band energies + centroid + rolloff + flux
  - No FFT recomputation — reuse what AudioAnalyzer already provides
  - ~50µs per frame on modern hardware
  - Exponential smoothing prevents jitter, fast attack for responsiveness
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  OUTPUT DATA
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SpectralState:
    """Complete spectral characterization of the current audio moment."""

    # ── Spectral Shape ──
    brightness: float = 0.5       # 0=dark/bassy, 1=bright/airy
    spread: float = 0.5           # 0=narrow (one band dominant), 1=wide (all bands active)
    flatness: float = 0.0         # 0=tonal/pitched, 1=noise-like/broadband
    tilt: float = 0.0             # -1=bottom-heavy, 0=balanced, +1=top-heavy

    # ── Onset Texture ──
    attack_sharpness: float = 0.0   # 0=soft onset (pad), 1=hard onset (hit/pluck)
    sustain_level: float = 0.5      # 0=staccato/transient, 1=sustained/held
    transient_density: float = 0.0  # onsets per second normalized (0=sparse, 1=dense)

    # ── Harmonic Content ──
    tonality: float = 0.5          # 0=inharmonic/noise, 1=strongly pitched
    harmonic_complexity: float = 0.5  # 0=simple sine, 1=rich harmonics (saw/square)
    pitch_stability: float = 0.5   # 0=sweeping/unstable, 1=steady pitch

    # ── Moment Character (composite) ──
    melodic_intensity: float = 0.0   # how much pitched musical content (not drums, not silence)
    wall_of_sound: float = 0.0      # full-spectrum saturation (drop wall)
    ethereal: float = 0.0           # spacious + high + soft + tonal (breakdown pads)
    aggressive: float = 0.0         # bright + harsh + loud + flat (drop leads/basses)
    rising: float = 0.0             # pitch/energy/density increasing (buildup character)

    # ── Instrument-ish classification (soft, overlapping probabilities) ──
    sounds_like_pad: float = 0.0     # sustained, soft onset, tonal, wide
    sounds_like_lead: float = 0.0    # sustained, bright, tonal, narrow
    sounds_like_bass: float = 0.0    # dark, tonal, narrow, powerful
    sounds_like_riser: float = 0.0   # rising pitch, noise-ish, building
    sounds_like_impact: float = 0.0  # very sharp onset, decaying, wide

    # ── Section evidence from spectral character ──
    spectral_says_breakdown: float = 0.0  # ethereal + low energy + sustained
    spectral_says_buildup: float = 0.0    # rising + increasing density + noise
    spectral_says_drop: float = 0.0       # wall_of_sound + aggressive + full spread
    spectral_says_melodic_moment: float = 0.0  # high melodic_intensity, low drum power


# ══════════════════════════════════════════════════════════════════════
#  SPECTRAL INTELLIGENCE ENGINE
# ══════════════════════════════════════════════════════════════════════

class SpectralIntelligence:
    """Lightweight spectral characterization from pre-computed audio features.

    Call update() every frame (~60fps). Reads 7-band energies +
    spectral_centroid + spectral_rolloff (already computed by AudioAnalyzer)
    and derives rich understanding of what's playing.
    """

    def __init__(self):
        self.state = SpectralState()

        # ── Smoothing state ──
        self._smooth_brightness: float = 0.5
        self._smooth_spread: float = 0.5
        self._smooth_flatness: float = 0.0
        self._smooth_tilt: float = 0.0
        self._smooth_tonality: float = 0.5
        self._smooth_complexity: float = 0.5
        self._smooth_pitch_stability: float = 0.5
        self._smooth_sustain: float = 0.5
        self._smooth_attack: float = 0.0
        self._smooth_melodic: float = 0.0

        # ── Onset detection state ──
        self._prev_total_energy: float = 0.0
        self._prev_band_energies: list = [0.0] * 7
        self._onset_history: list = []       # (time, magnitude) tuples
        self._onset_window: float = 2.0      # track onsets over 2 seconds

        # ── Energy envelope for sustain detection ──
        self._energy_envelope: float = 0.0   # fast-attack, slow-decay envelope
        self._energy_peak: float = 0.0       # recent peak for sustain ratio
        self._peak_decay_rate: float = 2.0   # seconds to decay peak

        # ── Pitch tracking (centroid stability) ──
        self._centroid_history: list = []     # recent centroid values
        self._centroid_window: int = 15       # frames to track (~250ms at 60fps)
        self._prev_centroid: float = 0.0

        # ── Harmonic ratio tracking ──
        # Band energy ratios that indicate harmonic structure
        self._band_ratio_history: list = []
        self._ratio_window: int = 10

    def update(
        self,
        # 7-band energies (normalized 0-1)
        sub_bass: float = 0.0,    # 20-60 Hz
        bass: float = 0.0,        # 60-250 Hz
        low_mid: float = 0.0,     # 250-500 Hz
        mid: float = 0.0,         # 500-2000 Hz
        high_mid: float = 0.0,    # 2000-4000 Hz
        high: float = 0.0,        # 4000-8000 Hz
        brilliance: float = 0.0,  # 8000-20000 Hz
        # Pre-computed spectral metrics
        spectral_centroid: float = 2000.0,  # Hz
        spectral_rolloff: float = 4000.0,   # Hz
        spectral_flux: float = 0.0,
        energy: float = 0.0,
        dt: float = 0.016,
        # Optional: drum state for melodic isolation
        drum_power: float = 0.0,
    ) -> SpectralState:
        """Analyze one frame. Returns updated SpectralState."""

        s = self.state
        bands = [sub_bass, bass, low_mid, mid, high_mid, high, brilliance]
        total = sum(bands) + 1e-10
        now_approx = sum(len(self._onset_history) for _ in [0])  # frame counter proxy

        # ══════════════════════════════════════════════════════════
        #  1. SPECTRAL SHAPE
        # ══════════════════════════════════════════════════════════

        # Brightness: normalized spectral centroid
        # EDM range: ~200Hz (sub bass) to ~8000Hz (bright leads)
        # Log scale for perceptual linearity
        raw_brightness = max(0.0, min(1.0,
            (math.log2(max(100.0, spectral_centroid)) - math.log2(100.0)) /
            (math.log2(10000.0) - math.log2(100.0))
        ))

        # Spread: how evenly distributed energy is across bands
        # High spread = full wall of sound. Low spread = one band dominates.
        band_fracs = [b / total for b in bands]
        # Entropy-based spread (normalized Shannon entropy)
        entropy = 0.0
        for frac in band_fracs:
            if frac > 1e-8:
                entropy -= frac * math.log2(frac)
        max_entropy = math.log2(7.0)  # max entropy for 7 bands
        raw_spread = entropy / max_entropy if max_entropy > 0 else 0.0

        # Flatness: spectral flatness approximation from bands
        # Geometric mean / arithmetic mean — 1.0 for white noise, 0.0 for pure tone
        log_sum = sum(math.log(max(1e-10, b)) for b in bands)
        geometric_mean = math.exp(log_sum / 7.0)
        arithmetic_mean = total / 7.0
        raw_flatness = min(1.0, geometric_mean / (arithmetic_mean + 1e-10))

        # Tilt: balance of low vs high frequency energy
        low_energy = sub_bass + bass + low_mid
        high_energy = high_mid + high + brilliance
        total_lh = low_energy + high_energy + 1e-10
        raw_tilt = (high_energy - low_energy) / total_lh  # -1 to +1

        # Smooth all shape metrics
        rate_shape = 6.0  # ~170ms smoothing
        self._smooth_brightness += (raw_brightness - self._smooth_brightness) * min(1.0, dt * rate_shape)
        self._smooth_spread += (raw_spread - self._smooth_spread) * min(1.0, dt * rate_shape)
        self._smooth_flatness += (raw_flatness - self._smooth_flatness) * min(1.0, dt * rate_shape)
        self._smooth_tilt += (raw_tilt - self._smooth_tilt) * min(1.0, dt * rate_shape)

        s.brightness = self._smooth_brightness
        s.spread = self._smooth_spread
        s.flatness = self._smooth_flatness
        s.tilt = self._smooth_tilt

        # ══════════════════════════════════════════════════════════
        #  2. ONSET TEXTURE
        # ══════════════════════════════════════════════════════════

        # Attack sharpness: how fast did energy rise this frame?
        # Compare current energy to previous — large positive delta = sharp attack
        energy_delta = energy - self._prev_total_energy
        raw_attack = max(0.0, min(1.0, energy_delta * 8.0))  # scale: 0.125 jump = full attack

        # Per-band onset detection (catches band-specific attacks)
        band_deltas = [max(0.0, bands[i] - self._prev_band_energies[i]) for i in range(7)]
        max_band_delta = max(band_deltas)
        raw_attack = max(raw_attack, min(1.0, max_band_delta * 10.0))

        # Track onset history for transient_density
        onset_threshold = 0.04
        if energy_delta > onset_threshold:
            t_approx = len(self._onset_history) * dt  # approximate time
            self._onset_history.append((t_approx, energy_delta))

        # Trim onset history to window
        if len(self._onset_history) > 200:
            self._onset_history = self._onset_history[-100:]

        # Transient density: onsets per second over recent window
        recent_onsets = len([o for o in self._onset_history[-int(self._onset_window / dt):]
                           if o[1] > onset_threshold]) if dt > 0 else 0
        raw_transient_density = min(1.0, recent_onsets / (self._onset_window * 8.0))  # 8 onsets/sec = max

        # Sustain level: energy envelope ratio (current vs recent peak)
        # Fast attack, slow decay envelope
        if energy > self._energy_envelope:
            self._energy_envelope = energy  # instant attack
        else:
            self._energy_envelope *= max(0.0, 1.0 - dt * 3.0)  # ~330ms decay

        if energy > self._energy_peak:
            self._energy_peak = energy
        else:
            self._energy_peak *= max(0.0, 1.0 - dt * self._peak_decay_rate)
        self._energy_peak = max(self._energy_peak, 0.01)

        # Sustain = how close current energy is to the envelope (high = sustained sound)
        raw_sustain = energy / (self._energy_peak + 1e-10)
        raw_sustain = min(1.0, raw_sustain)

        # Smooth onset metrics (fast attack for responsiveness)
        attack_smooth = 12.0  # fast: ~80ms
        sustain_smooth = 4.0  # slower: ~250ms
        self._smooth_attack += (raw_attack - self._smooth_attack) * min(1.0, dt * attack_smooth)
        self._smooth_sustain += (raw_sustain - self._smooth_sustain) * min(1.0, dt * sustain_smooth)

        s.attack_sharpness = self._smooth_attack
        s.sustain_level = self._smooth_sustain
        s.transient_density = raw_transient_density

        self._prev_total_energy = energy
        self._prev_band_energies = list(bands)

        # ══════════════════════════════════════════════════════════
        #  3. HARMONIC CONTENT
        # ══════════════════════════════════════════════════════════

        # Tonality: inverse of flatness, boosted by centroid stability
        # Tonal sounds have peaked spectra (low flatness) with stable pitch
        raw_tonality = 1.0 - raw_flatness

        # Harmonic complexity: how many bands have significant energy?
        # A simple sine has energy in ~1 band. A saw wave spreads across many.
        # But unlike spread, this counts active bands (above threshold), not entropy
        active_bands = sum(1 for b in bands if b > 0.02)
        raw_complexity = min(1.0, (active_bands - 1) / 5.0)  # 1 band=0, 6 bands=1

        # If it's also tonal (not noisy), more active bands = richer harmonics
        raw_complexity = raw_complexity * (0.3 + 0.7 * raw_tonality)

        # Pitch stability: how stable is the spectral centroid?
        self._centroid_history.append(spectral_centroid)
        if len(self._centroid_history) > self._centroid_window:
            self._centroid_history = self._centroid_history[-self._centroid_window:]

        if len(self._centroid_history) >= 3:
            centroid_vals = self._centroid_history
            centroid_mean = sum(centroid_vals) / len(centroid_vals)
            centroid_var = sum((c - centroid_mean) ** 2 for c in centroid_vals) / len(centroid_vals)
            # Normalize: std dev of 500Hz = unstable, <50Hz = very stable
            centroid_std = math.sqrt(centroid_var)
            raw_pitch_stability = max(0.0, 1.0 - centroid_std / 500.0)

            # Detect rising pitch (riser/buildup signal)
            if len(centroid_vals) >= 5:
                first_half = sum(centroid_vals[:len(centroid_vals)//2]) / max(1, len(centroid_vals)//2)
                second_half = sum(centroid_vals[len(centroid_vals)//2:]) / max(1, len(centroid_vals) - len(centroid_vals)//2)
                centroid_rise = (second_half - first_half) / (centroid_mean + 1e-10)
            else:
                centroid_rise = 0.0
        else:
            raw_pitch_stability = 0.5
            centroid_rise = 0.0

        # Smooth harmonic metrics
        rate_harmonic = 4.0  # ~250ms
        self._smooth_tonality += (raw_tonality - self._smooth_tonality) * min(1.0, dt * rate_harmonic)
        self._smooth_complexity += (raw_complexity - self._smooth_complexity) * min(1.0, dt * rate_harmonic)
        self._smooth_pitch_stability += (raw_pitch_stability - self._smooth_pitch_stability) * min(1.0, dt * rate_harmonic)

        s.tonality = self._smooth_tonality
        s.harmonic_complexity = self._smooth_complexity
        s.pitch_stability = self._smooth_pitch_stability

        # ══════════════════════════════════════════════════════════
        #  4. MOMENT CHARACTER (composites)
        # ══════════════════════════════════════════════════════════

        # Melodic intensity: how much pitched musical content (excluding drums)?
        # High tonality + high energy + low drum power + sustained = melodic moment
        non_drum_energy = max(0.0, energy - drum_power * 0.5)
        raw_melodic = (
            0.35 * s.tonality +
            0.25 * min(1.0, non_drum_energy * 1.5) +
            0.20 * s.sustain_level +
            0.20 * s.harmonic_complexity
        ) * max(0.2, 1.0 - drum_power * 0.5)  # reduce when drums dominate

        self._smooth_melodic += (raw_melodic - self._smooth_melodic) * min(1.0, dt * 5.0)
        s.melodic_intensity = self._smooth_melodic

        # Wall of sound: full-spectrum saturation
        s.wall_of_sound = min(1.0, (
            0.30 * s.spread +
            0.25 * min(1.0, energy * 1.5) +
            0.20 * s.harmonic_complexity +
            0.15 * (1.0 - s.flatness) +  # tonal wall, not noise
            0.10 * min(1.0, (sub_bass + bass) * 2.0)  # bass foundation
        ))

        # Ethereal: spacious + high + soft + tonal (breakdown pads)
        s.ethereal = min(1.0, (
            0.25 * max(0.0, s.brightness - 0.3) +
            0.25 * s.sustain_level +
            0.20 * s.tonality +
            0.15 * max(0.0, 1.0 - s.attack_sharpness) +
            0.15 * max(0.0, 1.0 - energy * 2.0)  # low energy
        )) * max(0.0, 1.0 - drum_power)  # zero when drums are loud

        # Aggressive: bright + harsh + loud + broad
        s.aggressive = min(1.0, (
            0.25 * s.brightness +
            0.25 * min(1.0, energy * 1.5) +
            0.20 * s.flatness +  # noisy/harsh
            0.15 * s.spread +
            0.15 * max(0.0, s.tilt)  # top-heavy spectrum
        ))

        # Rising: pitch/energy/density increasing (buildup character)
        rising_pitch = max(0.0, centroid_rise * 3.0)  # positive centroid trend
        rising_flux = min(1.0, spectral_flux * 2.0)   # high spectral change
        s.rising = min(1.0, (
            0.35 * min(1.0, rising_pitch) +
            0.25 * rising_flux +
            0.20 * max(0.0, s.flatness - 0.3) +  # noise increasing (riser)
            0.20 * max(0.0, s.brightness - 0.4)   # getting brighter
        ))

        # ══════════════════════════════════════════════════════════
        #  5. INSTRUMENT CLASSIFICATION (soft probabilities)
        # ══════════════════════════════════════════════════════════

        # Pad: sustained, soft onset, tonal, spread
        s.sounds_like_pad = min(1.0, (
            0.30 * s.sustain_level +
            0.25 * max(0.0, 1.0 - s.attack_sharpness) +
            0.25 * s.tonality +
            0.20 * s.spread
        )) * max(0.0, 1.0 - drum_power * 0.7)

        # Lead synth: sustained, bright, tonal, narrower
        s.sounds_like_lead = min(1.0, (
            0.30 * s.tonality +
            0.25 * s.brightness +
            0.20 * s.sustain_level +
            0.15 * s.harmonic_complexity +
            0.10 * max(0.0, 1.0 - s.spread)  # narrower than pad
        )) * max(0.0, 1.0 - drum_power * 0.5)

        # Bass: dark, tonal, narrow, powerful low end
        bass_presence = min(1.0, (sub_bass + bass) * 2.0)
        s.sounds_like_bass = min(1.0, (
            0.35 * bass_presence +
            0.25 * max(0.0, 1.0 - s.brightness) +
            0.20 * s.tonality +
            0.20 * max(0.0, 1.0 - s.tilt)  # bottom-heavy
        ))

        # Riser: rising pitch, noise-ish, building energy
        s.sounds_like_riser = min(1.0, (
            0.30 * s.rising +
            0.25 * max(0.0, s.flatness - 0.2) +
            0.25 * max(0.0, 1.0 - s.pitch_stability) +
            0.20 * s.brightness
        ))

        # Impact: very sharp onset, broad, decaying
        s.sounds_like_impact = min(1.0, (
            0.40 * s.attack_sharpness +
            0.25 * s.spread +
            0.20 * max(0.0, 1.0 - s.sustain_level) +
            0.15 * min(1.0, energy * 2.0)
        )) * min(1.0, s.attack_sharpness * 3.0)  # gate: only when there IS an attack

        # ══════════════════════════════════════════════════════════
        #  6. SECTION EVIDENCE FROM SPECTRAL CHARACTER
        # ══════════════════════════════════════════════════════════

        # Breakdown: ethereal + low energy + sustained + tonal
        s.spectral_says_breakdown = min(1.0, (
            0.30 * s.ethereal +
            0.25 * max(0.0, 1.0 - energy * 2.0) +
            0.20 * s.sustain_level +
            0.15 * s.sounds_like_pad +
            0.10 * s.tonality
        ))

        # Buildup: rising + increasing noise/density + riser present
        s.spectral_says_buildup = min(1.0, (
            0.30 * s.rising +
            0.25 * s.sounds_like_riser +
            0.20 * rising_flux +
            0.15 * s.flatness +  # noise increasing
            0.10 * s.brightness
        ))

        # Drop: wall of sound + aggressive + full spectrum + bass heavy
        s.spectral_says_drop = min(1.0, (
            0.25 * s.wall_of_sound +
            0.25 * s.aggressive +
            0.20 * s.spread +
            0.15 * s.sounds_like_bass +
            0.15 * min(1.0, energy * 1.5)
        ))

        # Melodic moment: high melodic intensity, not drums, sustained
        s.spectral_says_melodic_moment = min(1.0, (
            0.35 * s.melodic_intensity +
            0.25 * s.sounds_like_lead +
            0.20 * s.tonality +
            0.20 * max(0.0, 1.0 - drum_power)
        ))

        return s
