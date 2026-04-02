"""
Section Detector — The Authority on "Where Are We?"
=====================================================

Single responsibility: determine the current song section.

OWNERSHIP:
  - DrumIntelligence is the PRIMARY signal (65%)
  - AudioIntelligence is the CONFIRMER (20%)
  - MusicalIntelligence is the TIEBREAKER (15%, verse vs chorus)
  - StructurePredictor provides anticipatory hints

This service owns:
  - Section probability computation and blending
  - EMA smoothing with drum-adaptive rates
  - Confidence-gated state machine with min-dwell
  - Boundary detection (spectral flux N-of-M)
  - Drop fast-path (kick return = instant)
  - Breakdown fast-path (kick disappears = immediate)

It does NOT own:
  - Look selection (that's MusicalIntelligence → LookLibrary)
  - Energy intensity / dimmer scaling (that's AudioIntelligence)
  - Fixture control / DMX (that's EffectsEngine)
  - BPM / beat tracking (that's AudioAnalyzer)

CONSUMERS read from SectionState:
  - EffectsEngine: current section, section_changed_at, confidence
  - StructurePredictor: current section for pattern learning
  - LookLibrary: section for tag matching
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  OUTPUT DATA
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SectionState:
    """Everything consumers need to know about the current section."""

    section: str = "verse"              # current section name
    changed_at: float = 0.0             # timestamp of last section change
    time_in_section: float = 0.0        # seconds since last change

    # Probabilities (smoothed)
    probs: Dict[str, float] = field(default_factory=lambda: {
        "breakdown": 0.0, "verse": 0.5, "buildup": 0.0, "chorus": 0.0, "drop": 0.0
    })
    confidence: float = 0.5             # margin between top and second prob
    stable: bool = True                 # is the section state stable?

    # Drop state
    in_drop: bool = False               # currently in a confirmed drop
    drop_held_until: float = 0.0        # drop hold expiry time

    # Buildup tracking
    buildup_ramp_start: float = -999.0  # when buildup started (for ramp effects)
    buildup_ramp_progress: float = 0.0  # 0→1 progress through buildup

    # Drum evidence strength (how clear drums are about structure)
    drum_evidence_strength: float = 0.0

    # Boundary detection
    boundary_confirmed: bool = False    # spectral boundary just confirmed

    # Fast-stream outputs (for beat/accent detection in effects engine)
    onset_envelope: float = 0.0         # smoothed onset strength
    onset_peak_threshold: float = 0.02  # adaptive threshold
    onset_last_peak_time: float = -999.0  # when last onset peak occurred
    spectral_flux_running: float = 0.0  # smooth spectral flux


# ══════════════════════════════════════════════════════════════════════
#  SECTION DETECTOR
# ══════════════════════════════════════════════════════════════════════

class SectionDetector:
    """Confidence-gated section state machine.

    Call update() every frame with the latest analysis from all systems.
    Read the result from self.state (SectionState).
    """

    def __init__(self):
        self.state = SectionState()

        # ── Section probabilities (smoothed) ──
        self._section_probs: Dict[str, float] = {
            "breakdown": 0.0, "verse": 0.5, "buildup": 0.0, "chorus": 0.0, "drop": 0.0
        }

        # ── State machine internals ──
        self._section: str = "verse"
        self._section_changed_at: float = 0.0
        self._drop_until: float = -999.0
        self._last_impact: float = -999.0
        self._manual_hold_until: float = -999.0

        # ── Smoothing / hold config ──
        self._min_hold_bars: int = 8
        self._min_hold_s: float = 3.0
        self._buildup_ramp_start: float = -999.0

        # ── Fast stream: spectral flux onset ──
        self._prev_spectral_frame: list = [0.0] * 5
        self._onset_envelope: float = 0.0
        self._onset_peak_threshold: float = 0.02
        self._onset_last_peak_time: float = -999.0
        self._onset_cooldown_s: float = 0.15
        self._spectral_flux_running: float = 0.0

        # ── Energy history for boundary detection ──
        self._energy_history: list = []
        self._energy_window: float = 8.0
        self._prev_energy: float = 0.0
        self._prev_bass: float = 0.0

        # ── Boundary N-of-M confirmation ──
        self._boundary_prob_history: list = []
        self._boundary_confirm_threshold: int = 3
        self._boundary_confirm_window: int = 5
        self._boundary_last_confirmed: float = -999.0

        # ── Drum evidence strength tracker ──
        self._drum_evidence_strength: float = 0.0

    # ──────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────────

    def set_manual_hold(self, until: float):
        """API override: hold current section until the given timestamp."""
        self._manual_hold_until = until

    def update(
        self,
        now: float,
        dt: float,
        # Raw audio features
        energy: float,
        bass: float,
        mid: float,
        high: float,
        spectral_flux: float,
        is_beat: bool,
        bpm: float,
        # Intelligence outputs (all optional — degrade gracefully)
        drum_state=None,            # DrumState from DrumIntelligence
        audio_intel_state=None,     # AudioIntelligenceState from AudioIntelligence
        musical_fingerprint=None,   # MusicalFingerprint from MusicalIntelligence
        prediction_state=None,      # PredictionState from StructurePredictor
        spectral_state=None,        # SpectralState from SpectralIntelligence
    ) -> SectionState:
        """Run one frame of section detection. Returns updated SectionState."""

        if now < self._manual_hold_until:
            self._update_output(now)
            return self.state

        beats_per_sec = bpm / 60.0
        e, b, m, h, f = energy, bass, mid, high, spectral_flux

        # ══════════════════════════════════════════════════════════
        #  FAST STREAM: Spectral flux onset envelope
        # ══════════════════════════════════════════════════════════
        prev = self._prev_spectral_frame
        flux_raw = (max(0.0, e - prev[0]) + max(0.0, b - prev[1]) +
                    max(0.0, m - prev[2]) * 0.6 + max(0.0, h - prev[3]) * 0.3)
        self._prev_spectral_frame = [e, b, m, h, f]

        # Fast attack / slow decay
        if flux_raw > self._onset_envelope:
            self._onset_envelope += (flux_raw - self._onset_envelope) * min(1.0, dt * 25.0)
        else:
            self._onset_envelope *= max(0.0, 1.0 - dt * 4.0)

        # Adaptive threshold
        self._onset_peak_threshold += (self._onset_envelope * 0.6 - self._onset_peak_threshold) * min(1.0, dt * 1.5)
        self._onset_peak_threshold = max(0.008, self._onset_peak_threshold)

        # Peak picking with cooldown
        is_onset_peak = (
            self._onset_envelope > self._onset_peak_threshold * 1.8 and
            (now - self._onset_last_peak_time) > self._onset_cooldown_s
        )
        if is_onset_peak:
            self._onset_last_peak_time = now

        # Smooth spectral flux for section analysis
        self._spectral_flux_running += (flux_raw - self._spectral_flux_running) * min(1.0, dt * 2.0)

        # ══════════════════════════════════════════════════════════
        #  Rolling energy history
        # ══════════════════════════════════════════════════════════
        self._energy_history.append((now, e, b, m, h, flux_raw))
        cutoff = now - self._energy_window
        self._energy_history = [x for x in self._energy_history if x[0] >= cutoff]
        hist = self._energy_history
        n = len(hist)

        # ══════════════════════════════════════════════════════════
        #  COMPOSITE SIGNAL (for silence detection + impulse)
        # ══════════════════════════════════════════════════════════
        sig = max(e, b * 0.8, 0.35 * e + 0.30 * b + 0.20 * m + 0.15 * h)

        # ══════════════════════════════════════════════════════════
        #  RELATIVE CHANGE (boundary + impulse detection)
        # ══════════════════════════════════════════════════════════
        de = e - self._prev_energy
        db = b - self._prev_bass
        dm = m - (hist[-2][3] if n >= 2 else m)

        impulse = max(de, db, dm * 0.5)
        has_impulse = impulse > 0.015 and sig > 0.1

        # Multi-frame impulse (catches 2-3 frame ramps)
        if n >= 10:
            recent_e = sum(x[1] for x in hist[-5:]) / 5.0
            older_e = sum(x[1] for x in hist[-10:-5]) / 5.0
            recent_b = sum(x[2] for x in hist[-5:]) / 5.0
            older_b = sum(x[2] for x in hist[-10:-5]) / 5.0
            multi_impulse = max(recent_e - older_e, recent_b - older_b)
            if multi_impulse > 0.03 and sig > 0.1:
                has_impulse = True
                impulse = max(impulse, multi_impulse)

        # ══════════════════════════════════════════════════════════
        #  BOUNDARY PROBABILITY (N-of-M confirmation)
        # ══════════════════════════════════════════════════════════
        boundary_signal = self._spectral_flux_running * 2.0 + abs(de) + abs(db)
        boundary_prob = min(1.0, boundary_signal / 0.15)
        self._boundary_prob_history.append(boundary_prob)
        if len(self._boundary_prob_history) > self._boundary_confirm_window:
            self._boundary_prob_history = self._boundary_prob_history[-self._boundary_confirm_window:]

        frames_above = sum(1 for p in self._boundary_prob_history if p > 0.5)
        boundary_confirmed = (
            frames_above >= self._boundary_confirm_threshold and
            (now - self._boundary_last_confirmed) > 2.0
        )
        if boundary_confirmed:
            self._boundary_last_confirmed = now

        # ══════════════════════════════════════════════════════════
        #  SECTION PROBABILITIES
        # ══════════════════════════════════════════════════════════
        # MusicalIntelligence provides the TIEBREAKER (15% weight).
        # Good for verse vs chorus (melody vs groove feel), not for
        # structure boundaries (that's drums).
        probs = {"breakdown": 0.0, "verse": 0.0, "buildup": 0.0, "chorus": 0.0, "drop": 0.0}

        fp = musical_fingerprint
        if fp is not None:
            drv = fp.drive
            den = fp.density
            amb = fp.ambiance
            act = fp.element_activity
            tonal = fp.tonal_vs_noisy
            perc = fp.percussive_vs_sustained
            dom = fp.dominant

            # Breakdown: spacious, sparse, low drive, pads
            probs["breakdown"] = (
                0.30 * amb + 0.25 * (1.0 - drv) + 0.20 * (1.0 - den) +
                0.15 * dom.pad + 0.10 * perc
            )

            # Verse: moderate, stable, tonal
            drv_mid = 1.0 - abs(drv - 0.4) * 2.5
            den_mid = 1.0 - abs(den - 0.4) * 2.5
            act_low = 1.0 - act
            probs["verse"] = max(0.0, (
                0.30 * max(0.0, drv_mid) + 0.25 * max(0.0, den_mid) +
                0.20 * max(0.0, act_low) + 0.15 * tonal + 0.10 * (1.0 - amb)
            ))

            # Buildup: activity rising, noise, spectral change
            probs["buildup"] = (
                0.35 * act + 0.25 * dom.noise +
                0.20 * min(1.0, self._spectral_flux_running / 0.04) +
                0.10 * (1.0 - perc) + 0.10 * min(1.0, drv * 1.5)
            )

            # Chorus: driving, full, melodic, tonal
            probs["chorus"] = (
                0.25 * drv + 0.25 * den + 0.20 * tonal +
                0.15 * dom.lead_synth + 0.15 * (1.0 - amb)
            )

            # Drop: max drive, dense, dry, bass+drums, percussive
            bass_drums = dom.bass_synth + dom.drums
            probs["drop"] = (
                0.25 * drv + 0.20 * den + 0.20 * (1.0 - amb) +
                0.20 * min(1.0, bass_drums) + 0.15 * (1.0 - perc)
            )

            # Impulse boost for drop
            if has_impulse:
                probs["drop"] += min(0.25, impulse * 2.0)

        else:
            # Fallback: basic energy
            probs["breakdown"] = max(0.0, 1.0 - sig / 0.2) * 0.5
            probs["verse"] = max(0.0, 1.0 - abs(sig - 0.35) / 0.3) * 0.4
            probs["buildup"] = min(1.0, self._spectral_flux_running / 0.05) * 0.3
            probs["chorus"] = min(1.0, sig / 0.5) * 0.4
            probs["drop"] = (0.3 if has_impulse else 0.0) + min(1.0, sig / 0.5) * 0.3

        # ══════════════════════════════════════════════════════════
        #  DRUM-PRIMARY EVIDENCE BLEND
        # ══════════════════════════════════════════════════════════
        # Drums ARE the structure. 65% drums, 20% audio intel, 15% musical.
        ds = drum_state
        if ds is not None:
            drum_evidence = {
                "breakdown": ds.drums_say_breakdown,
                "buildup": ds.drums_say_buildup,
                "drop": ds.drums_say_drop,
                "verse": ds.drums_say_verse,
                "chorus": ds.drums_say_verse * 0.8,
            }
            self._drum_evidence_strength = max(drum_evidence.values())

            if audio_intel_state is not None:
                ai_ev = audio_intel_state.section_evidence
                for k in probs:
                    probs[k] = (drum_evidence.get(k, 0.0) * 0.65 +
                                ai_ev.get(k, 0.0) * 0.20 +
                                probs[k] * 0.15)
            else:
                for k in probs:
                    probs[k] = drum_evidence.get(k, 0.0) * 0.75 + probs[k] * 0.25
        elif audio_intel_state is not None:
            self._drum_evidence_strength = 0.0
            ai_ev = audio_intel_state.section_evidence
            for k in probs:
                probs[k] = probs[k] * 0.55 + ai_ev.get(k, 0.0) * 0.45
        else:
            self._drum_evidence_strength = 0.0

        # ══════════════════════════════════════════════════════════
        #  SPECTRAL INTELLIGENCE CORRECTION
        # ══════════════════════════════════════════════════════════
        # SpectralIntelligence acts as a corrective signal, not a primary
        # evidence source. Its main value: preventing misclassification
        # when drums are absent but music is still high-energy (synth solos,
        # melodic builds, bass drops without kick patterns).
        ss = spectral_state
        if ss is not None:
            # Melodic moment correction: if drums say breakdown but spectral
            # says high melodic intensity, this isn't a quiet breakdown —
            # it's a melodic verse/chorus moment. Shift evidence accordingly.
            if ss.spectral_says_melodic_moment > 0.4 and probs.get("breakdown", 0) > 0.3:
                melodic_correction = ss.spectral_says_melodic_moment * 0.3
                probs["breakdown"] = max(0.0, probs["breakdown"] - melodic_correction)
                probs["chorus"] = probs.get("chorus", 0.0) + melodic_correction * 0.6
                probs["verse"] = probs.get("verse", 0.0) + melodic_correction * 0.4

            # Buildup boost: spectral rising (pitch sweep, noise build)
            # reinforces drum-based buildup evidence
            if ss.spectral_says_buildup > 0.3:
                probs["buildup"] = probs.get("buildup", 0.0) + ss.spectral_says_buildup * 0.15

            # Drop reinforcement: wall_of_sound + aggressive = drop character
            if ss.spectral_says_drop > 0.4:
                probs["drop"] = probs.get("drop", 0.0) + ss.spectral_says_drop * 0.10

        # Normalize
        total_p = sum(probs.values())
        if total_p > 0:
            for k in probs:
                probs[k] /= total_p

        current = self._section or "verse"
        drum_str = self._drum_evidence_strength

        # ══════════════════════════════════════════════════════════
        #  EMA SMOOTHING (drum-adaptive rate)
        # ══════════════════════════════════════════════════════════
        smooth_rate = 2.0 + drum_str * 4.0

        if current == "buildup" and probs.get("drop", 0) > 0.25:
            smooth_rate = 12.0  # ~80ms
        elif probs.get("drop", 0) > 0.45:
            smooth_rate = 8.0   # ~125ms
        elif probs.get("breakdown", 0) > 0.5 and current != "breakdown":
            smooth_rate = 6.0   # ~170ms

        # Kick return instant override: bypass smoothing for drop
        if ds is not None and ds.kick_return > 0.5:
            self._section_probs["drop"] = max(
                self._section_probs.get("drop", 0.0),
                probs.get("drop", 0.0)
            )

        for k in probs:
            self._section_probs[k] += (probs[k] - self._section_probs[k]) * min(1.0, dt * smooth_rate)

        # ══════════════════════════════════════════════════════════
        #  STATE MACHINE: confidence-gated transitions
        # ══════════════════════════════════════════════════════════
        time_in_current = now - self._section_changed_at

        # Adaptive min hold based on drum clarity
        bar_duration = 4.0 / beats_per_sec
        drum_clear = drum_str > 0.5
        hold_bars = 4.0 if drum_clear else self._min_hold_bars
        min_hold_time = max(
            self._min_hold_s * (0.5 if drum_clear else 1.0),
            hold_bars * bar_duration
        )

        # Winner + confidence
        prob_winner = max(self._section_probs, key=self._section_probs.get)
        prob_confidence = self._section_probs.get(prob_winner, 0.0)

        sorted_probs = sorted(self._section_probs.values(), reverse=True)
        margin = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else sorted_probs[0]
        section_confidence = margin
        section_stable = margin > 0.10

        # ── DROP TRANSITION (drum-primary) ──
        drop_cooldown = 2.0
        past_cooldown = (now - self._last_impact) > drop_cooldown
        drop_transition = False

        # 1. Kick return = instant drop
        if ds is not None and ds.kick_return > 0.3 and past_cooldown:
            drop_transition = True

        # 2. Buildup→drop: low threshold
        elif current == "buildup" and prob_winner == "drop" and past_cooldown:
            drop_transition = prob_confidence > 0.20

        # 3. Any→drop with drum evidence
        elif prob_winner == "drop" and past_cooldown:
            threshold = 0.28 if drum_clear else 0.35
            drop_transition = prob_confidence > threshold

        # Structure predictor boost
        if (not drop_transition and prediction_state is not None and
                prediction_state.drop_imminent and prediction_state.confidence > 0.3 and
                current == "buildup" and prob_winner == "drop" and past_cooldown):
            drop_transition = prob_confidence > 0.18

        # ── DECIDE TARGET SECTION ──
        if drop_transition:
            self._last_impact = now
            self._drop_until = now + bar_duration * 8
            target = "drop"
            kick_ret = ds.kick_return if ds is not None else 0.0
            logger.info(
                f">>> DROP DETECTED <<< confidence={prob_confidence:.3f} "
                f"kick_return={kick_ret:.2f} drum_strength={drum_str:.2f} "
                f"probs={dict((k, round(v, 3)) for k, v in self._section_probs.items())}"
            )
        elif now < self._drop_until:
            target = "drop"
        elif sig < 0.03:
            target = "breakdown"
        # Drum-clear breakdown: kick gone + low power = immediate
        elif (ds is not None and ds.drum_power < 0.10 and
              ds.kick_confidence < 0.08 and prob_winner == "breakdown" and
              current != "breakdown"):
            target = "breakdown"
        elif time_in_current < min_hold_time and prob_confidence < (0.40 if drum_clear else 0.55):
            target = current
        elif boundary_confirmed and section_stable and prob_winner != current:
            target = prob_winner
        elif drum_clear and prob_confidence > 0.35 and time_in_current >= min_hold_time and prob_winner != current:
            target = prob_winner
        elif prob_confidence > 0.50 and time_in_current >= min_hold_time and prob_winner != current:
            target = prob_winner
        elif prob_confidence > 0.32 and time_in_current >= min_hold_time * 1.5 and prob_winner != current:
            target = prob_winner
        else:
            target = current

        # ── BUILDUP RAMP TRACKING ──
        if target == "buildup" and current != "buildup":
            self._buildup_ramp_start = now
        elif target != "buildup":
            self._buildup_ramp_start = -999.0

        # ── APPLY SECTION CHANGE ──
        self._set_section(target, now)
        self._prev_energy = e
        self._prev_bass = b

        # ── UPDATE OUTPUT STATE ──
        self._update_output(now, boundary_confirmed, section_confidence, section_stable)
        return self.state

    # ──────────────────────────────────────────────────────────────
    #  INTERNALS
    # ──────────────────────────────────────────────────────────────

    def _set_section(self, section_name: str, now: float):
        section_name = (section_name or "verse").lower()
        if section_name == self._section:
            return
        logger.info(f"SECTION CHANGE: {self._section} -> {section_name}")
        self._section = section_name
        self._section_changed_at = now

    def _update_output(self, now: float, boundary_confirmed: bool = False,
                       confidence: float = 0.5, stable: bool = True):
        s = self.state
        s.section = self._section
        s.changed_at = self._section_changed_at
        s.time_in_section = now - self._section_changed_at
        s.probs = dict(self._section_probs)
        s.confidence = confidence
        s.stable = stable
        s.in_drop = now < self._drop_until
        s.drop_held_until = self._drop_until
        s.drum_evidence_strength = self._drum_evidence_strength
        s.boundary_confirmed = boundary_confirmed

        # Buildup ramp progress (0→1)
        if self._section == "buildup" and self._buildup_ramp_start > 0:
            elapsed = now - self._buildup_ramp_start
            # Typical buildup is 8-16 bars. Normalize to ~16 bars.
            bpm_estimate = 128.0  # reasonable EDM default
            bars_16_duration = 16.0 * (4.0 / (bpm_estimate / 60.0))
            s.buildup_ramp_start = self._buildup_ramp_start
            s.buildup_ramp_progress = min(1.0, elapsed / bars_16_duration)
        else:
            s.buildup_ramp_start = -999.0
            s.buildup_ramp_progress = 0.0

        # Fast-stream outputs
        s.onset_envelope = self._onset_envelope
        s.onset_peak_threshold = self._onset_peak_threshold
        s.onset_last_peak_time = self._onset_last_peak_time
        s.spectral_flux_running = self._spectral_flux_running
