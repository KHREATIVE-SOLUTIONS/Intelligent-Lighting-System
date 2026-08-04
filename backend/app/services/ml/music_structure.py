"""
Music Structure Analyzer
========================

Offline structure analysis plus phrase and anticipation bookkeeping.

**This module no longer classifies sections in real time.** It used to run an
energy state machine of its own, which published a section label into the ML
pipeline and competed with the renderer's detector for control of the same
`SectionManager`. The one live detector is
`app.services.lighting.section_manager.StreamingSectionDetector`; this module
drives an instance of it purely to know whether the music is building, and
reports `SectionType.UNKNOWN` at zero confidence unless a genuine external
source (All-In-One pre-analysis) has labelled the track.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from collections import deque
import logging
import time

from ..lighting.section_manager import StreamingSectionDetector

logger = logging.getLogger(__name__)


class SectionType(Enum):
    """Musical section types for structure analysis."""
    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    DROP = "drop"
    BREAKDOWN = "breakdown"
    BUILD_UP = "build_up"
    OUTRO = "outro"
    INSTRUMENTAL = "instrumental"
    SOLO = "solo"
    UNKNOWN = "unknown"


@dataclass
class SectionInfo:
    """Information about the current musical section."""
    section_type: SectionType = SectionType.UNKNOWN
    confidence: float = 0.0
    progress: float = 0.0            # 0.0 (just started) to 1.0 (about to end)
    bars_elapsed: int = 0
    estimated_bars_remaining: int = 0
    phrase_position: int = 1          # Bar within phrase (1-4 or 1-8)
    phrase_length: int = 4            # Expected phrase length in bars
    is_section_boundary: bool = False


@dataclass
class TransitionPrediction:
    """Prediction of upcoming section transitions."""
    predicted_next_section: SectionType = SectionType.UNKNOWN
    bars_until_transition: int = 0
    transition_confidence: float = 0.0
    is_buildup: bool = False
    buildup_progress: float = 0.0    # 0.0 = just started, 1.0 = about to drop
    transition_type: str = "none"    # "drop", "breakdown", "section_change", "none"


@dataclass
class StructureAnalysis:
    """Complete structure analysis output."""
    current_section: SectionInfo = field(default_factory=SectionInfo)
    transition: TransitionPrediction = field(default_factory=TransitionPrediction)
    bpm: float = 120.0
    time_signature: str = "4/4"
    bar_number: int = 0
    beat_in_bar: int = 1
    timestamp: float = 0.0


class MusicStructureAnalyzer:
    """Offline structure analysis plus real-time anticipation.

    Provides:
    1. All-In-One Music Structure Analyzer for offline/pre-analysis
    2. Phrase and bar bookkeeping
    3. Build-up/drop anticipation, taken from the one live section detector

    Section *classification* in real time is not this class's job; see the
    module docstring.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.allin1_model = None
        self.loaded = False

        # Real-time state
        self._current_section = SectionType.UNKNOWN
        self._section_start_bar = 0
        self._bar_counter = 0
        self._beat_counter = 0
        self._bpm = 120.0
        self._beats_per_bar = 4

        # Energy tracking for transition prediction
        self._energy_history: deque = deque(maxlen=64)  # 64 bars of energy

        # Buildup detection, from the shared detector
        self._detector = StreamingSectionDetector()
        self._detected_section = "verse"
        self._buildup_start_bar: Optional[int] = None
        self._in_buildup = False

        # Pre-analyzed structure (from offline analysis)
        self._preanalyzed_sections: List[Dict] = []
        self._preanalysis_offset = 0.0  # Timestamp offset for alignment

    async def load(self) -> bool:
        """Load the All-In-One structure analysis model."""
        try:
            import allin1
            self.allin1_model = allin1
            self.loaded = True
            logger.info("All-In-One Music Structure Analyzer loaded")
            return True
        except ImportError:
            logger.warning(
                "allin1 package not installed. Using heuristic structure detection. "
                "Install with: pip install allin1"
            )
            return False

    async def analyze_file(self, audio_path: str) -> List[Dict]:
        """Pre-analyze an entire audio file for section boundaries.

        Returns list of sections with timestamps. Used for pre-show
        analysis when tracks are known in advance.
        """
        if not self.allin1_model:
            logger.warning("All-In-One model not loaded, cannot analyze file")
            return []

        try:
            result = self.allin1_model.analyze(audio_path)

            sections = []
            for segment in result.segments:
                section_type = self._map_allin1_label(segment.label)
                sections.append({
                    "start": segment.start,
                    "end": segment.end,
                    "section_type": section_type.value,
                    "label": segment.label,
                })

            self._preanalyzed_sections = sections
            logger.info(
                "Pre-analyzed %d sections from %s", len(sections), audio_path
            )
            return sections
        except Exception as e:
            logger.error("File analysis error: %s", e)
            return []

    def set_preanalyzed_sections(
        self, sections: List[Dict], offset: float = 0.0
    ):
        """Set pre-analyzed section data for real-time lookup.

        Args:
            sections: List of {start, end, section_type} dicts
            offset: Timestamp offset for alignment with playback
        """
        self._preanalyzed_sections = sections
        self._preanalysis_offset = offset

    def update_beat(
        self,
        is_beat: bool,
        is_downbeat: bool,
        bpm: float,
        energy: float,
        bass: float,
        spectral_flux: float,
        spectral_centroid: float = 0.0,
    ) -> StructureAnalysis:
        """Update with new beat information and return current structure.

        Called on every audio analysis frame. The reported section comes from
        pre-analysis only; the build-up signal comes from the shared live
        detector.

        Args:
            is_beat: Whether a beat was detected
            is_downbeat: Whether a downbeat (bar start) was detected
            bpm: Current BPM estimate
            energy: Overall energy (0-1)
            bass: Bass energy (0-1)
            spectral_flux: Rate of spectral change
            spectral_centroid: Spectral centroid frequency
        """
        self._bpm = bpm
        timestamp = time.time()

        if is_beat:
            self._beat_counter += 1

        if is_downbeat:
            self._bar_counter += 1
            self._energy_history.append(energy)

        self._update_anticipation(
            energy=energy,
            bass=bass,
            spectral_flux=spectral_flux,
            is_beat=is_beat,
            is_downbeat=is_downbeat,
            bpm=bpm,
        )

        beat_in_bar = (self._beat_counter % self._beats_per_bar) + 1
        bars_in_section = self._bar_counter - self._section_start_bar

        # Calculate phrase position (4-bar phrases)
        phrase_len = 4
        phrase_pos = (bars_in_section % phrase_len) + 1

        # Estimate progress through section
        typical_section_bars = self._get_typical_section_length(self._current_section)
        progress = min(1.0, bars_in_section / typical_section_bars) if typical_section_bars > 0 else 0.0

        # Check pre-analyzed sections
        section_from_preanalysis = self._lookup_preanalyzed_section(timestamp)
        if section_from_preanalysis:
            self._current_section = section_from_preanalysis

        # Transition prediction
        transition = self._predict_transition(
            energy, bass, spectral_flux, bars_in_section
        )

        return StructureAnalysis(
            current_section=SectionInfo(
                section_type=self._current_section,
                # Zero without pre-analysis: the confidence gate downstream is
                # what stops this becoming a second section authority.
                confidence=0.9 if self._preanalyzed_sections else 0.0,
                progress=progress,
                bars_elapsed=bars_in_section,
                estimated_bars_remaining=max(0, typical_section_bars - bars_in_section),
                phrase_position=phrase_pos,
                phrase_length=phrase_len,
                is_section_boundary=is_downbeat and bars_in_section == 0,
            ),
            transition=transition,
            bpm=bpm,
            time_signature=f"{self._beats_per_bar}/4",
            bar_number=self._bar_counter,
            beat_in_bar=beat_in_bar,
            timestamp=timestamp,
        )

    def _update_anticipation(
        self,
        *,
        energy: float,
        bass: float,
        spectral_flux: float,
        is_beat: bool,
        is_downbeat: bool,
        bpm: float,
    ):
        """Track build-up state from the one live section detector.

        Deliberately does not touch `_current_section`: this class no longer
        classifies sections in real time.
        """
        decision = self._detector.update(
            None,
            energy=energy,
            bass=bass,
            spectral_flux=spectral_flux,
            is_beat=is_beat,
            beat_number=self._beat_counter,
            bpm=bpm,
            is_downbeat_event=is_downbeat,
        )
        self._detected_section = decision.section
        if not decision.changed:
            return

        self._section_start_bar = self._bar_counter
        if decision.section == "buildup":
            self._in_buildup = True
            self._buildup_start_bar = self._bar_counter
        else:
            self._in_buildup = False
            self._buildup_start_bar = None

    def _predict_transition(
        self,
        energy: float,
        bass: float,
        spectral_flux: float,
        bars_in_section: int,
    ) -> TransitionPrediction:
        """Predict upcoming section transitions.

        Analyzes energy trajectories and section progress to anticipate
        drops, breakdowns, and section changes 4-8 bars ahead.
        """
        prediction = TransitionPrediction()

        if len(self._energy_history) < 4:
            return prediction

        recent_energy = list(self._energy_history)[-8:] if len(self._energy_history) >= 8 else list(self._energy_history)
        energy_slope = (recent_energy[-1] - recent_energy[0]) / len(recent_energy)

        # Buildup detection with progress tracking
        if self._in_buildup and self._buildup_start_bar is not None:
            buildup_bars = self._bar_counter - self._buildup_start_bar
            # Typical buildup is 8-16 bars
            prediction.is_buildup = True
            prediction.buildup_progress = min(1.0, buildup_bars / 12.0)
            prediction.bars_until_transition = max(0, 12 - buildup_bars)
            prediction.predicted_next_section = SectionType.DROP
            prediction.transition_type = "drop"
            prediction.transition_confidence = min(0.9, 0.3 + buildup_bars * 0.05)

        # Approaching section boundary (typical section lengths)
        elif bars_in_section > 0:
            typical_len = self._get_typical_section_length(self._current_section)
            remaining = max(0, typical_len - bars_in_section)

            if remaining <= 4 and bars_in_section >= 4:
                prediction.bars_until_transition = remaining
                prediction.transition_confidence = 0.4 + (1 - remaining / 4) * 0.3

                # Predict what comes next
                prediction.predicted_next_section = self._get_likely_next_section()
                if prediction.predicted_next_section == SectionType.DROP:
                    prediction.transition_type = "drop"
                elif prediction.predicted_next_section == SectionType.BREAKDOWN:
                    prediction.transition_type = "breakdown"
                else:
                    prediction.transition_type = "section_change"

        # Energy rising without being in a detected buildup
        elif energy_slope > 0.03 and not self._in_buildup:
            prediction.bars_until_transition = max(4, int(8 - energy_slope * 100))
            prediction.transition_type = "section_change"
            prediction.transition_confidence = 0.3

        return prediction

    def _get_typical_section_length(self, section: SectionType) -> int:
        """Get typical length in bars for a section type."""
        lengths = {
            SectionType.INTRO: 8,
            SectionType.VERSE: 16,
            SectionType.CHORUS: 8,
            SectionType.BRIDGE: 8,
            SectionType.DROP: 16,
            SectionType.BREAKDOWN: 8,
            SectionType.BUILD_UP: 8,
            SectionType.OUTRO: 8,
            SectionType.INSTRUMENTAL: 8,
            SectionType.SOLO: 8,
            SectionType.UNKNOWN: 8,
        }
        return lengths.get(section, 8)

    def _get_likely_next_section(self) -> SectionType:
        """Predict the likely next section based on current section."""
        transitions = {
            SectionType.INTRO: SectionType.VERSE,
            SectionType.VERSE: SectionType.CHORUS,
            SectionType.CHORUS: SectionType.VERSE,
            SectionType.BRIDGE: SectionType.CHORUS,
            SectionType.DROP: SectionType.BREAKDOWN,
            SectionType.BREAKDOWN: SectionType.BUILD_UP,
            SectionType.BUILD_UP: SectionType.DROP,
            SectionType.OUTRO: SectionType.OUTRO,
            SectionType.INSTRUMENTAL: SectionType.VERSE,
            SectionType.SOLO: SectionType.CHORUS,
            SectionType.UNKNOWN: SectionType.VERSE,
        }
        return transitions.get(self._current_section, SectionType.UNKNOWN)

    def _lookup_preanalyzed_section(
        self, timestamp: float
    ) -> Optional[SectionType]:
        """Look up current section from pre-analyzed data."""
        if not self._preanalyzed_sections:
            return None

        adjusted_time = timestamp - self._preanalysis_offset
        for section in self._preanalyzed_sections:
            if section["start"] <= adjusted_time < section["end"]:
                try:
                    return SectionType(section["section_type"])
                except ValueError:
                    return self._map_allin1_label(section.get("label", ""))
        return None

    def _map_allin1_label(self, label: str) -> SectionType:
        """Map All-In-One label strings to SectionType enum."""
        label_lower = label.lower().strip()
        mapping = {
            "intro": SectionType.INTRO,
            "verse": SectionType.VERSE,
            "chorus": SectionType.CHORUS,
            "bridge": SectionType.BRIDGE,
            "drop": SectionType.DROP,
            "breakdown": SectionType.BREAKDOWN,
            "build": SectionType.BUILD_UP,
            "build_up": SectionType.BUILD_UP,
            "buildup": SectionType.BUILD_UP,
            "outro": SectionType.OUTRO,
            "instrumental": SectionType.INSTRUMENTAL,
            "inst": SectionType.INSTRUMENTAL,
            "solo": SectionType.SOLO,
        }
        for key, value in mapping.items():
            if key in label_lower:
                return value
        return SectionType.UNKNOWN

    def reset(self):
        """Reset all state for a new track."""
        self._current_section = SectionType.UNKNOWN
        self._section_start_bar = 0
        self._bar_counter = 0
        self._beat_counter = 0
        self._energy_history.clear()
        self._detector.reset()
        self._detected_section = "verse"
        self._buildup_start_bar = None
        self._in_buildup = False
        self._preanalyzed_sections = []

    def get_info(self) -> Dict[str, Any]:
        """Get analyzer status."""
        return {
            "loaded": self.loaded,
            "has_allin1": self.allin1_model is not None,
            "current_section": self._current_section.value,
            "detected_section": self._detected_section,
            "bar_count": self._bar_counter,
            "in_buildup": self._in_buildup,
            "preanalyzed_sections": len(self._preanalyzed_sections),
        }
