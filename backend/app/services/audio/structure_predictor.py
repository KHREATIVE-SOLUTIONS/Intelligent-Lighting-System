"""
Structure Predictor — Anticipatory Song Structure Analysis
==========================================================

Predicts upcoming song sections BEFORE they happen so the lighting
can prepare, creating dramatically more impactful transitions.

THREE PREDICTION LAYERS:

1. RISER COUNTDOWN
   When a riser/buildup is detected, estimates time-to-drop based on:
   - Riser duration so far (EDM risers are typically 4, 8, or 16 bars)
   - Energy slope (steeper = shorter riser)
   - Spectral density increase rate
   Outputs: predicted_drop_in_bars, riser_progress (0→1)

2. PATTERN MEMORY (within-song learning)
   EDM tracks are repetitive. The predictor remembers every section
   transition it's seen in this song and uses that to predict:
   - If we saw buildup→drop at bars 24-32 and we're now in a buildup
     at bar 88, expect a drop around bar 96 (same 8-bar pattern)
   - If breakdowns last 16 bars in this song, start preparing for
     the buildup at bar 12 of the current breakdown
   Outputs: predicted_next_section, confidence, predicted_bars_until

3. ENERGY CURVE MATCHING
   Compares the current energy trajectory against common EDM templates:
   - 16-bar verse → 8-bar buildup → 16-bar drop → 8-bar breakdown
   - 32-bar verse → 16-bar buildup → 32-bar drop → 16-bar breakdown
   - 8-bar intro → 16-bar verse → 8-bar build → 8-bar drop (short form)
   Uses dynamic time warping-lite to find best matching template position.
   Outputs: template_match_confidence, predicted_next_section

COMBINED OUTPUT:
   All three layers feed a single PredictionState with:
   - predicted_next: what section is most likely coming next
   - confidence: how sure we are (0-1)
   - bars_until: estimated bars until the transition
   - preparation_intensity: how aggressively to prepare (0-1)
     (drives pre-drop dimming, movement tightening, etc.)

DESIGN PRINCIPLE:
   Wrong predictions should be invisible. Preparation is always subtle
   enough that it looks intentional even if the drop doesn't come.
   "A moment of restraint is never a mistake." — LD wisdom
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
class SectionMemory:
    """Record of a section that was observed in this song."""
    section: str           # section type
    start_bar: int         # bar number when it started
    duration_bars: int     # how many bars it lasted (0 if still active)
    avg_energy: float      # average energy during this section
    peak_energy: float     # peak energy during this section
    ended: bool = False    # has this section ended?


@dataclass
class TransitionMemory:
    """Record of a section transition observed in this song."""
    from_section: str
    to_section: str
    at_bar: int
    from_duration_bars: int   # how long the from_section lasted


@dataclass
class PredictionState:
    """Combined prediction output."""
    # What's coming next
    predicted_next: str = ""           # predicted next section
    confidence: float = 0.0            # 0-1 how confident
    bars_until: float = 999.0          # estimated bars until transition
    preparation_intensity: float = 0.0 # 0-1 how aggressively to prepare

    # Riser-specific
    riser_active: bool = False
    riser_progress: float = 0.0        # 0→1 how far through the riser
    riser_predicted_duration: float = 8.0  # predicted total riser bars

    # Pattern memory
    pattern_match: str = ""            # which historical pattern matched
    pattern_confidence: float = 0.0

    # Energy template
    template_match: str = ""           # which template matched
    template_phase: float = 0.0        # 0-1 where we are in the template

    # Derived signals for lighting
    drop_imminent: bool = False        # drop predicted within 2 bars
    pre_drop_dim: float = 0.0          # 0-1 dimmer reduction for pre-drop
    pre_drop_tighten: float = 0.0      # 0-1 movement tightening
    post_drop_boost: float = 0.0       # 0-1 extra intensity right after drop


# ══════════════════════════════════════════════════════════════════════
#  EDM STRUCTURE TEMPLATES
# ══════════════════════════════════════════════════════════════════════

# Each template is a list of (section, duration_bars) tuples
# representing a common EDM arrangement pattern.
# The predictor matches the current song against these.

EDM_TEMPLATES = {
    "standard_128": [
        ("verse", 16), ("buildup", 8), ("drop", 16), ("breakdown", 8),
        ("verse", 16), ("buildup", 8), ("drop", 16), ("breakdown", 16),
    ],
    "short_form": [
        ("verse", 8), ("buildup", 8), ("drop", 8), ("breakdown", 8),
        ("verse", 8), ("buildup", 8), ("drop", 16), ("breakdown", 8),
    ],
    "extended_build": [
        ("breakdown", 16), ("verse", 16), ("buildup", 16), ("drop", 32),
        ("breakdown", 8), ("buildup", 8), ("drop", 16), ("breakdown", 16),
    ],
    "festival_banger": [
        ("verse", 8), ("buildup", 16), ("drop", 16), ("breakdown", 4),
        ("buildup", 8), ("drop", 32), ("breakdown", 16),
    ],
    "progressive": [
        ("verse", 32), ("buildup", 8), ("chorus", 16), ("verse", 16),
        ("buildup", 8), ("drop", 16), ("breakdown", 16),
    ],
}


# ══════════════════════════════════════════════════════════════════════
#  STRUCTURE PREDICTOR
# ══════════════════════════════════════════════════════════════════════

class StructurePredictor:
    """Predicts upcoming song sections for anticipatory lighting."""

    def __init__(self):
        self.state = PredictionState()

        # ── Section history (within-song learning) ──
        self._section_history: List[SectionMemory] = []
        self._transition_history: List[TransitionMemory] = []
        self._current_section: str = ""
        self._current_section_start_bar: int = 0
        self._current_section_energy_sum: float = 0.0
        self._current_section_energy_count: int = 0
        self._current_section_peak: float = 0.0

        # ── Riser tracking ──
        self._riser_start_bar: int = -1
        self._riser_start_time: float = -1.0
        self._riser_active: bool = False
        self._riser_energy_at_start: float = 0.0
        self._riser_energy_slope: float = 0.0

        # ── Energy history for template matching ──
        self._bar_energy_history: List[Tuple[int, float, str]] = []  # (bar, avg_energy, section)
        self._last_bar_processed: int = -1

        # ── Template matching state ──
        self._best_template: str = ""
        self._best_template_offset: int = 0
        self._template_confidence: float = 0.0
        self._template_last_check_bar: int = -1

        # ── Post-drop tracking ──
        self._last_drop_bar: int = -999
        self._drop_just_hit: bool = False

    def update(self, section: str, bar_clock: int, energy: float,
               bpm: float, riser_active: bool, riser_intensity: float,
               trajectory_direction: str, dt: float = 0.016) -> PredictionState:
        """Update predictions based on current song state.

        Args:
            section: Current detected section
            bar_clock: Current bar number
            energy: Current energy level (0-1)
            bpm: Current BPM
            riser_active: Whether AudioIntelligence detects a riser
            riser_intensity: Riser intensity from AudioIntelligence (0-1)
            trajectory_direction: "building", "sustaining", "falling", "anticipation"
            dt: Delta time

        Returns:
            PredictionState with all predictions
        """
        # ── Track section changes ──
        self._track_section(section, bar_clock, energy)

        # ── Per-bar energy logging ──
        if bar_clock != self._last_bar_processed:
            if self._current_section_energy_count > 0:
                avg_e = self._current_section_energy_sum / self._current_section_energy_count
            else:
                avg_e = energy
            self._bar_energy_history.append((bar_clock, avg_e, section))
            # Keep last 256 bars (~8 minutes at 128bpm)
            if len(self._bar_energy_history) > 256:
                self._bar_energy_history = self._bar_energy_history[-256:]
            self._last_bar_processed = bar_clock

        # Accumulate energy for current section
        self._current_section_energy_sum += energy
        self._current_section_energy_count += 1
        self._current_section_peak = max(self._current_section_peak, energy)

        # ── Run all prediction layers ──
        self._predict_riser_countdown(section, bar_clock, energy, bpm,
                                      riser_active, riser_intensity, trajectory_direction)
        self._predict_from_pattern_memory(section, bar_clock)
        self._predict_from_energy_templates(section, bar_clock, energy)

        # ── Combine predictions ──
        self._combine_predictions(section, bar_clock, energy, dt)

        return self.state

    # ══════════════════════════════════════════════════════════════════
    #  SECTION TRACKING (builds the memory)
    # ══════════════════════════════════════════════════════════════════

    def _track_section(self, section: str, bar_clock: int, energy: float):
        """Track section changes to build pattern memory."""
        if section != self._current_section:
            # Close out the previous section
            if self._current_section and self._current_section_energy_count > 0:
                prev_duration = bar_clock - self._current_section_start_bar
                avg_e = self._current_section_energy_sum / self._current_section_energy_count
                mem = SectionMemory(
                    section=self._current_section,
                    start_bar=self._current_section_start_bar,
                    duration_bars=max(1, prev_duration),
                    avg_energy=avg_e,
                    peak_energy=self._current_section_peak,
                    ended=True,
                )
                self._section_history.append(mem)

                # Record transition
                self._transition_history.append(TransitionMemory(
                    from_section=self._current_section,
                    to_section=section,
                    at_bar=bar_clock,
                    from_duration_bars=max(1, prev_duration),
                ))

                # Track drops
                if section == "drop":
                    self._last_drop_bar = bar_clock
                    self._drop_just_hit = True

            # Start new section
            self._current_section = section
            self._current_section_start_bar = bar_clock
            self._current_section_energy_sum = 0.0
            self._current_section_energy_count = 0
            self._current_section_peak = 0.0

            # Keep history bounded
            if len(self._section_history) > 64:
                self._section_history = self._section_history[-64:]
            if len(self._transition_history) > 64:
                self._transition_history = self._transition_history[-64:]

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 1: RISER COUNTDOWN
    # ══════════════════════════════════════════════════════════════════

    def _predict_riser_countdown(self, section: str, bar_clock: int,
                                 energy: float, bpm: float,
                                 riser_active: bool, riser_intensity: float,
                                 trajectory_direction: str):
        """Predict drop timing from riser characteristics."""
        s = self.state

        if riser_active and not self._riser_active:
            # Riser just started
            self._riser_active = True
            self._riser_start_bar = bar_clock
            self._riser_start_time = time.monotonic()
            self._riser_energy_at_start = energy
        elif not riser_active and self._riser_active:
            # Riser ended (drop likely just happened or riser fizzled)
            self._riser_active = False

        if self._riser_active:
            riser_bars = max(1, bar_clock - self._riser_start_bar)

            # Estimate total riser duration from:
            # 1) Historical buildups in this song
            # 2) Energy slope (steeper = shorter riser)
            # 3) Standard EDM riser lengths (4, 8, 16 bars)

            # Check history: how long do buildups last in THIS song?
            buildup_durations = [
                mem.duration_bars for mem in self._section_history
                if mem.section == "buildup" and mem.ended and mem.duration_bars >= 2
            ]
            if buildup_durations:
                # Use the most recent buildup duration as best estimate
                historical_estimate = buildup_durations[-1]
            else:
                historical_estimate = None

            # Energy slope estimate: if energy is rising fast, shorter riser
            energy_delta = energy - self._riser_energy_at_start
            if riser_bars > 0 and energy_delta > 0:
                # At current rate, how many bars to reach peak (~0.85)?
                bars_to_peak = (0.85 - energy) / (energy_delta / riser_bars + 0.001)
                slope_estimate = riser_bars + max(2, int(bars_to_peak))
            else:
                slope_estimate = None

            # Snap to nearest standard EDM riser length
            standard_lengths = [4, 8, 12, 16, 24, 32]

            # Choose best estimate
            if historical_estimate:
                predicted_duration = historical_estimate
            elif slope_estimate and 2 <= slope_estimate <= 40:
                # Snap to nearest standard length
                predicted_duration = min(standard_lengths, key=lambda x: abs(x - slope_estimate))
            else:
                # Default: assume 8-bar riser if early, 16 if energy is low
                predicted_duration = 8 if energy > 0.35 else 16

            # Ensure prediction is at least as long as current riser
            if predicted_duration < riser_bars:
                # We've passed the predicted end — extend to next standard
                for sl in standard_lengths:
                    if sl > riser_bars:
                        predicted_duration = sl
                        break
                else:
                    predicted_duration = riser_bars + 4

            bars_remaining = max(0, predicted_duration - riser_bars)
            progress = min(1.0, riser_bars / max(1, predicted_duration))

            s.riser_active = True
            s.riser_progress = progress
            s.riser_predicted_duration = predicted_duration
            s.bars_until = bars_remaining
            s.predicted_next = "drop"
            s.drop_imminent = bars_remaining <= 2

            # Confidence increases as riser progresses
            s.confidence = max(s.confidence, min(0.95, 0.3 + progress * 0.65))
        else:
            s.riser_active = False
            s.riser_progress = 0.0
            # Don't clear other predictions — pattern memory may still be active

        # Also detect buildup section as implicit riser (even if AudioIntel
        # doesn't flag a spectral riser, the section detector says buildup)
        if section == "buildup" and not s.riser_active:
            buildup_bars = bar_clock - self._current_section_start_bar

            # Check how long buildups last in this song
            buildup_durations = [
                mem.duration_bars for mem in self._section_history
                if mem.section == "buildup" and mem.ended and mem.duration_bars >= 2
            ]
            if buildup_durations:
                expected = buildup_durations[-1]
            elif trajectory_direction == "building":
                expected = 8
            else:
                expected = 12

            bars_remaining = max(0, expected - buildup_bars)
            progress = min(1.0, buildup_bars / max(1, expected))

            if progress > 0.3:  # only predict after at least 30% of expected buildup
                s.predicted_next = "drop"
                s.bars_until = min(s.bars_until, bars_remaining)
                s.confidence = max(s.confidence, min(0.8, 0.2 + progress * 0.6))
                s.drop_imminent = bars_remaining <= 2

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 2: PATTERN MEMORY
    # ══════════════════════════════════════════════════════════════════

    def _predict_from_pattern_memory(self, section: str, bar_clock: int):
        """Predict next section from patterns observed earlier in this song."""
        s = self.state

        if len(self._transition_history) < 2:
            return  # need at least 2 transitions to learn patterns

        current_duration = bar_clock - self._current_section_start_bar

        # Find all previous instances of the SAME section type
        same_section_memories = [
            mem for mem in self._section_history
            if mem.section == section and mem.ended
        ]

        if not same_section_memories:
            return

        # What typically follows this section type in THIS song?
        following_sections = {}
        for trans in self._transition_history:
            if trans.from_section == section:
                key = trans.to_section
                if key not in following_sections:
                    following_sections[key] = []
                following_sections[key].append(trans.from_duration_bars)

        if not following_sections:
            return

        # Most common next section
        best_next = max(following_sections, key=lambda k: len(following_sections[k]))
        durations = following_sections[best_next]
        avg_duration = sum(durations) / len(durations)
        frequency = len(durations) / len([t for t in self._transition_history if t.from_section == section])

        # Predict: based on how long this section type typically lasts
        bars_remaining = max(0, avg_duration - current_duration)

        # Confidence: higher if we've seen this pattern multiple times
        confidence = min(0.85, 0.3 + frequency * 0.3 + len(durations) * 0.1)

        if confidence > s.pattern_confidence:
            s.pattern_match = f"{section}→{best_next} (seen {len(durations)}x, avg {avg_duration:.0f} bars)"
            s.pattern_confidence = confidence

            # Only update main prediction if pattern memory is stronger
            if confidence > s.confidence * 0.8:  # slight preference for riser countdown
                if s.predicted_next == "" or (s.predicted_next == best_next):
                    s.predicted_next = best_next
                    s.bars_until = min(s.bars_until, bars_remaining)
                    s.confidence = max(s.confidence, confidence)
                elif bars_remaining < 4:
                    # Pattern memory overrides if transition is very close
                    s.predicted_next = best_next
                    s.bars_until = bars_remaining
                    s.confidence = confidence

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 3: ENERGY CURVE MATCHING
    # ══════════════════════════════════════════════════════════════════

    def _predict_from_energy_templates(self, section: str, bar_clock: int,
                                       energy: float):
        """Match current energy curve against known EDM structure templates."""
        s = self.state

        # Only re-check templates every 4 bars (expensive-ish)
        if bar_clock - self._template_last_check_bar < 4:
            return
        self._template_last_check_bar = bar_clock

        if len(self._bar_energy_history) < 8:
            return  # need some history

        # Build the observed section sequence from history
        observed_sections = []
        for mem in self._section_history:
            observed_sections.append((mem.section, mem.duration_bars))
        # Add current section (ongoing)
        current_dur = bar_clock - self._current_section_start_bar
        if current_dur > 0:
            observed_sections.append((section, current_dur))

        if len(observed_sections) < 2:
            return

        # Match against each template
        best_template = ""
        best_score = 0.0
        best_offset = 0
        best_next_section = ""
        best_bars_until = 999

        for tname, template in EDM_TEMPLATES.items():
            score, offset, next_sect, bars_left = self._match_template(
                observed_sections, template, section, current_dur
            )
            if score > best_score:
                best_score = score
                best_template = tname
                best_offset = offset
                best_next_section = next_sect
                best_bars_until = bars_left

        if best_score > 0.3:
            s.template_match = best_template
            s.template_phase = best_offset / max(1, sum(d for _, d in EDM_TEMPLATES.get(best_template, [])))
            template_confidence = min(0.7, best_score)

            # Update main prediction if template is informative
            if best_next_section and template_confidence > 0.3:
                if s.predicted_next == "":
                    s.predicted_next = best_next_section
                    s.bars_until = min(s.bars_until, best_bars_until)
                    s.confidence = max(s.confidence, template_confidence * 0.7)
                elif s.predicted_next == best_next_section:
                    # Reinforces existing prediction
                    s.confidence = min(0.95, s.confidence + template_confidence * 0.15)

    def _match_template(self, observed: List[Tuple[str, int]],
                        template: List[Tuple[str, int]],
                        current_section: str, current_duration: int
                        ) -> Tuple[float, int, str, int]:
        """Score how well observed sections match a template.

        Returns: (score, offset_bars, predicted_next_section, bars_until_next)
        """
        if not observed or not template:
            return 0.0, 0, "", 999

        # Try aligning the observed sequence at different template offsets
        best_score = 0.0
        best_offset = 0
        best_next = ""
        best_bars_until = 999

        # Flatten template into (section, start_bar, end_bar) list
        flat_template = []
        bar_pos = 0
        for sect, dur in template:
            flat_template.append((sect, bar_pos, bar_pos + dur))
            bar_pos += dur
        total_template_bars = bar_pos

        # Try different offsets: align current section with each template section
        for t_idx, (t_sect, t_start, t_end) in enumerate(flat_template):
            if t_sect != current_section:
                continue

            # Align: current section starts at t_start in template
            # Check if duration is roughly right
            t_dur = t_end - t_start
            dur_ratio = current_duration / max(1, t_dur)
            if dur_ratio > 2.0 or (current_duration > 4 and dur_ratio < 0.2):
                continue  # duration mismatch too large

            # Score: check preceding sections match
            score = 0.0
            matches = 0
            total_checked = 0

            # Check the last few observed sections against template
            for obs_idx in range(len(observed) - 1, max(0, len(observed) - 5), -1):
                obs_sect, obs_dur = observed[obs_idx]
                # Find corresponding template position
                check_t_idx = t_idx - (len(observed) - 1 - obs_idx)
                if 0 <= check_t_idx < len(flat_template):
                    t_s, _, _ = flat_template[check_t_idx]
                    total_checked += 1
                    if t_s == obs_sect:
                        matches += 1

            if total_checked > 0:
                score = matches / total_checked

            # Duration match bonus
            if 0.5 <= dur_ratio <= 1.5:
                score += 0.2

            if score > best_score:
                best_score = score
                best_offset = t_start

                # Predict next: what comes after current template section?
                bars_remaining_in_current = max(0, t_dur - current_duration)
                if t_idx + 1 < len(flat_template):
                    best_next = flat_template[t_idx + 1][0]
                    best_bars_until = bars_remaining_in_current
                else:
                    # At end of template — wrap or predict nothing
                    best_next = ""
                    best_bars_until = 999

        return best_score, best_offset, best_next, best_bars_until

    # ══════════════════════════════════════════════════════════════════
    #  COMBINE PREDICTIONS → PREPARATION SIGNALS
    # ══════════════════════════════════════════════════════════════════

    def _combine_predictions(self, section: str, bar_clock: int,
                             energy: float, dt: float):
        """Combine all prediction layers into preparation signals for lighting."""
        s = self.state

        # ── Drop imminent check ──
        s.drop_imminent = (
            s.predicted_next == "drop" and
            s.bars_until <= 2 and
            s.confidence > 0.4
        )

        # ── Pre-drop preparation ──
        # Gradually increase preparation as we get closer to predicted drop
        if s.predicted_next == "drop" and s.confidence > 0.3:
            if s.bars_until <= 0:
                # Drop should be happening NOW — maximum preparation
                s.preparation_intensity = 1.0
            elif s.bars_until <= 2:
                # 1-2 bars out — strong preparation
                s.preparation_intensity = 0.7 + 0.3 * (1.0 - s.bars_until / 2.0)
            elif s.bars_until <= 4:
                # 3-4 bars out — moderate preparation
                s.preparation_intensity = 0.3 + 0.4 * (1.0 - s.bars_until / 4.0)
            elif s.bars_until <= 8:
                # 5-8 bars out — subtle preparation
                s.preparation_intensity = 0.1 + 0.2 * (1.0 - s.bars_until / 8.0)
            else:
                s.preparation_intensity = 0.0

            # Scale by confidence
            s.preparation_intensity *= s.confidence

            # Pre-drop dim: reduce intensity to create contrast for the drop
            # Maximum 40% reduction (enough for impact, not enough to notice if wrong)
            s.pre_drop_dim = s.preparation_intensity * 0.4

            # Pre-drop tighten: slow and tighten movements
            s.pre_drop_tighten = s.preparation_intensity * 0.5
        else:
            # Smooth decay when no drop predicted
            s.preparation_intensity *= max(0.0, 1.0 - dt * 3.0)
            s.pre_drop_dim *= max(0.0, 1.0 - dt * 3.0)
            s.pre_drop_tighten *= max(0.0, 1.0 - dt * 3.0)

        # ── Post-drop boost ──
        # Extra intensity right after a drop lands (first 2 bars)
        bars_since_drop = bar_clock - self._last_drop_bar
        if self._drop_just_hit or (section == "drop" and bars_since_drop <= 2):
            s.post_drop_boost = max(0.0, 1.0 - bars_since_drop * 0.3)
            self._drop_just_hit = False
        else:
            s.post_drop_boost *= max(0.0, 1.0 - dt * 4.0)

    # ══════════════════════════════════════════════════════════════════
    #  PUBLIC QUERY METHODS
    # ══════════════════════════════════════════════════════════════════

    def get_section_history(self) -> List[SectionMemory]:
        """Get all observed sections in this song."""
        return list(self._section_history)

    def get_transition_history(self) -> List[TransitionMemory]:
        """Get all observed transitions in this song."""
        return list(self._transition_history)

    def is_drop_imminent(self) -> bool:
        """Quick check: is a drop predicted within 2 bars?"""
        return self.state.drop_imminent

    def get_preparation_intensity(self) -> float:
        """How aggressively should lighting prepare? (0-1)"""
        return self.state.preparation_intensity
