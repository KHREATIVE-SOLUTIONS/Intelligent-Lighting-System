"""
Vocal Analyzer Service
======================

Two-layer vocal awareness for intelligent lighting:

LAYER 1 — Vocal Cadence (lightweight, every frame):
  Detects vocal presence, rhythm, and pitch contour from audio spectral
  features WITHOUT needing speech recognition. Maps to movement bounce,
  tilt accents, and energy modulation.

LAYER 2 — Lyric Transcription (heavier, every ~3-5 seconds):
  Uses OpenAI Whisper (base model, ~74M params) to transcribe vocals,
  then matches keywords to mood/color themes. E.g.:
    "girls" → pink/magenta palette
    "sad" / "cry" → blue/cool palette
    "fire" / "burn" → red-orange/warm palette
    "love" / "heart" → deep red palette
    "night" / "dark" → deep blue/purple palette

ETHEREAL DETECTION:
  Identifies spacey, emotional, sustained moments from audio character:
  low bass, high sustain, sparse onsets, high spectral centroid.
  Triggers slow fly-out movements and pastel/cool color shifts.
"""

import asyncio
import numpy as np
import time
import logging
import math
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  KEYWORD → MOOD → COLOR THEME DICTIONARY
# ══════════════════════════════════════════════════════════════════════
# Each theme has: (dominant_r, dominant_g, dominant_b), (accent_r, accent_g, accent_b), mood_name
# Themes are checked in priority order (first match wins)

@dataclass
class LyricTheme:
    """A color theme triggered by lyric keywords."""
    name: str                        # human-readable name
    keywords: List[str]              # trigger words (lowercase)
    dominant: Tuple[float, float, float]  # dominant RGB (0-1)
    accent: Tuple[float, float, float]    # accent RGB (0-1)
    mood: str                        # mood category
    warmth: float                    # 0=cold, 1=warm
    energy: float                    # 0=calm, 1=intense
    priority: int = 0               # higher = checked first


# Ordered by priority (specific → general)
LYRIC_THEMES: List[LyricTheme] = [
    # ── Specific content themes ──
    LyricTheme(
        name="girls_feminine",
        keywords=["girl", "girls", "her", "she", "woman", "women", "lady", "ladies",
                  "queen", "princess", "goddess", "mama", "baby girl", "shawty"],
        dominant=(1.0, 0.0, 0.55),    # hot pink
        accent=(0.85, 0.4, 1.0),      # soft lavender-pink
        mood="feminine", warmth=0.65, energy=0.6, priority=10,
    ),
    LyricTheme(
        name="love_romance",
        keywords=["love", "heart", "kiss", "hold me", "touch", "forever",
                  "romance", "darling", "babe", "together", "mine", "yours",
                  "passion", "desire", "devotion", "adore"],
        dominant=(0.9, 0.0, 0.15),     # deep red
        accent=(1.0, 0.3, 0.5),        # rose pink
        mood="romantic", warmth=0.85, energy=0.5, priority=9,
    ),
    LyricTheme(
        name="sad_emotional",
        keywords=["sad", "cry", "tears", "alone", "lonely", "broken",
                  "pain", "hurt", "miss you", "gone", "lost", "empty",
                  "sorrow", "grief", "goodbye", "farewell", "regret"],
        dominant=(0.05, 0.15, 0.7),    # deep blue
        accent=(0.2, 0.4, 0.9),        # lighter blue
        mood="melancholy", warmth=0.15, energy=0.2, priority=9,
    ),
    LyricTheme(
        name="anger_aggression",
        keywords=["fight", "war", "rage", "angry", "hate", "destroy",
                  "kill", "blood", "savage", "beast", "monster", "demon",
                  "hell", "burn it", "revenge"],
        dominant=(0.9, 0.0, 0.0),      # pure red
        accent=(1.0, 0.3, 0.0),        # orange-red
        mood="aggressive", warmth=0.9, energy=0.95, priority=8,
    ),
    LyricTheme(
        name="fire_heat",
        keywords=["fire", "flame", "burn", "hot", "heat", "blaze",
                  "inferno", "lit", "smoke", "ashes"],
        dominant=(1.0, 0.25, 0.0),     # fire orange
        accent=(1.0, 0.7, 0.0),        # golden yellow
        mood="fiery", warmth=1.0, energy=0.85, priority=8,
    ),
    LyricTheme(
        name="night_dark",
        keywords=["night", "dark", "midnight", "shadow", "moon", "stars",
                  "black", "twilight", "dusk", "dreams", "sleep", "nightmare"],
        dominant=(0.08, 0.0, 0.35),    # deep indigo
        accent=(0.15, 0.05, 0.6),      # dark purple
        mood="nocturnal", warmth=0.1, energy=0.3, priority=7,
    ),
    LyricTheme(
        name="sky_freedom",
        keywords=["sky", "fly", "free", "freedom", "wings", "soar",
                  "clouds", "heaven", "high", "above", "air", "wind",
                  "breathe", "float", "rise"],
        dominant=(0.3, 0.7, 1.0),      # sky blue
        accent=(0.9, 0.95, 1.0),       # white-blue
        mood="ethereal", warmth=0.3, energy=0.4, priority=7,
    ),
    LyricTheme(
        name="nature_earth",
        keywords=["ocean", "sea", "water", "rain", "river", "forest",
                  "tree", "earth", "mountain", "sun", "sunrise", "sunset",
                  "flower", "garden", "spring"],
        dominant=(0.0, 0.7, 0.4),      # emerald green
        accent=(0.2, 0.9, 0.7),        # teal
        mood="natural", warmth=0.5, energy=0.4, priority=6,
    ),
    LyricTheme(
        name="party_celebration",
        keywords=["party", "dance", "club", "tonight", "celebrate",
                  "turn up", "vibe", "energy", "move", "bounce",
                  "hands up", "jump", "let's go", "wild", "crazy"],
        dominant=(1.0, 0.0, 0.7),      # magenta
        accent=(0.0, 1.0, 0.8),        # neon cyan
        mood="party", warmth=0.6, energy=0.95, priority=6,
    ),
    LyricTheme(
        name="money_luxury",
        keywords=["money", "cash", "gold", "rich", "diamond", "ice",
                  "drip", "flex", "boss", "king", "crown", "chain",
                  "rollie", "lambo", "gucci", "bands"],
        dominant=(1.0, 0.85, 0.0),     # gold
        accent=(0.9, 0.9, 0.9),        # platinum/silver
        mood="luxury", warmth=0.75, energy=0.7, priority=5,
    ),
    LyricTheme(
        name="spiritual_transcendent",
        keywords=["god", "angel", "soul", "spirit", "pray", "faith",
                  "light", "holy", "divine", "blessed", "grace",
                  "universe", "cosmic", "eternal", "infinity"],
        dominant=(0.9, 0.8, 1.0),      # soft lavender
        accent=(1.0, 1.0, 0.85),       # warm white
        mood="transcendent", warmth=0.5, energy=0.3, priority=5,
    ),
    # ── General energy/mood fallbacks ──
    LyricTheme(
        name="happy_positive",
        keywords=["happy", "smile", "joy", "beautiful", "wonderful",
                  "amazing", "sunshine", "bright", "good", "great",
                  "perfect", "yeah", "woo"],
        dominant=(1.0, 0.8, 0.0),      # sunny yellow
        accent=(1.0, 0.5, 0.0),        # warm orange
        mood="joyful", warmth=0.8, energy=0.7, priority=3,
    ),
    LyricTheme(
        name="chill_relaxed",
        keywords=["chill", "relax", "easy", "slow", "smooth", "cool",
                  "mellow", "lazy", "peace", "calm", "quiet", "gentle"],
        dominant=(0.1, 0.5, 0.7),      # steel blue
        accent=(0.3, 0.7, 0.6),        # sage teal
        mood="chill", warmth=0.3, energy=0.2, priority=3,
    ),
]


@dataclass
class VocalState:
    """Current state of vocal analysis."""
    # Cadence layer (updated every frame)
    vocal_present: bool = False         # is someone singing/rapping right now?
    vocal_energy: float = 0.0           # vocal band energy (0-1)
    vocal_rhythm: float = 0.0           # rhythmic activity of vocal (0-1)
    vocal_pitch_rising: bool = False    # pitch trend going up?
    vocal_pitch_falling: bool = False   # pitch trend going down?
    vocal_cadence_phase: float = 0.0    # 0-1 phase of vocal rhythm cycle
    vocal_sustain: float = 0.0          # how sustained/legato the vocal is (0-1)

    # Ethereal detection
    is_ethereal: bool = False           # ethereal/spacey moment detected
    ethereal_intensity: float = 0.0     # 0-1 how ethereal

    # Lyric layer (updated every ~3-5 seconds)
    last_transcription: str = ""        # raw Whisper text
    active_theme: Optional[str] = None  # current matched theme name
    theme_confidence: float = 0.0       # 0-1 how strongly theme matches
    theme_dominant: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    theme_accent: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    theme_warmth: float = 0.5
    theme_energy: float = 0.5
    theme_mood: str = ""

    # Timing
    last_transcription_time: float = 0.0
    theme_hold_until: float = 0.0       # keep theme for at least this long


class VocalAnalyzer:
    """Two-layer vocal awareness: cadence (every frame) + lyrics (every ~3-5s)."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.state = VocalState()

        # ── Cadence detection state ──
        # Vocal frequency range: ~80Hz-1100Hz fundamental, ~1kHz-4kHz formants
        self._vocal_band_low = 200    # Hz — lower bound of vocal detection
        self._vocal_band_high = 4000  # Hz — upper bound
        self._vocal_energy_history = deque(maxlen=30)   # ~0.5s at 60fps
        self._vocal_rhythm_history = deque(maxlen=60)   # ~1s
        self._vocal_pitch_history = deque(maxlen=20)    # for trend detection
        self._vocal_onset_history = deque(maxlen=40)
        self._prev_vocal_energy = 0.0

        # ── Ethereal detection state ──
        self._ethereal_score_history = deque(maxlen=90)  # ~1.5s
        self._onset_density_history = deque(maxlen=120)  # ~2s

        # ── Whisper transcription state ──
        self._whisper_model = None
        self._whisper_available = False
        self._audio_buffer = deque(maxlen=sample_rate * 5)  # 5-second rolling buffer
        self._transcription_interval = 3.5  # seconds between transcriptions
        self._last_transcription_time = 0.0
        self._transcription_history = deque(maxlen=10)  # last 10 transcriptions
        self._theme_hold_duration = 8.0  # hold a theme for at least 8 seconds

        # Theme matching state
        self._active_theme_obj: Optional[LyricTheme] = None
        self._theme_keyword_counts: Dict[str, int] = {}

    async def initialize_whisper(self):
        """Load Whisper model (call once at startup)."""
        try:
            import whisper
            logger.info("Loading Whisper base model for lyric transcription...")
            self._whisper_model = whisper.load_model("base")
            self._whisper_available = True
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.warning(
                "openai-whisper not installed. Lyric transcription disabled. "
                "Install with: pip install openai-whisper"
            )
            self._whisper_available = False
        except Exception as e:
            logger.warning(f"Failed to load Whisper model: {e}. Lyric transcription disabled.")
            self._whisper_available = False

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 1: VOCAL CADENCE (lightweight, every frame)
    # ══════════════════════════════════════════════════════════════════

    def update_cadence(self, audio_chunk: np.ndarray, frequency_bands: Dict[str, float],
                       spectral_centroid: float, onset_envelope: float,
                       bass: float, energy: float, dt: float):
        """Update vocal cadence detection from current audio frame.

        This runs every frame (~60fps) and is computationally cheap.
        Uses frequency band energies to detect vocal presence and rhythm
        WITHOUT needing speech recognition.

        Args:
            audio_chunk: Raw audio samples (float32)
            frequency_bands: Dict of band name → energy (from audio analyzer)
            spectral_centroid: Current spectral centroid in Hz
            onset_envelope: Current onset strength
            bass: Bass energy (0-1)
            energy: Total energy (0-1)
            dt: Delta time since last frame
        """
        # Extract vocal-range energy from frequency bands
        # Vocals live primarily in mid (500-2000Hz) and high_mid (2000-4000Hz)
        mid_energy = float(frequency_bands.get("mid", 0.0))
        high_mid_energy = float(frequency_bands.get("high_mid", 0.0))
        low_mid_energy = float(frequency_bands.get("low_mid", 0.0))

        # Vocal energy: weighted combination of vocal-range bands
        # Subtract bass to isolate vocal from kick/bass
        vocal_e = (mid_energy * 0.5 + high_mid_energy * 0.35 + low_mid_energy * 0.15)
        vocal_e = max(0.0, vocal_e - bass * 0.3)  # remove bass bleed
        vocal_e = min(1.0, vocal_e)

        self._vocal_energy_history.append(vocal_e)

        # Vocal presence detection: vocal energy above threshold AND
        # spectral centroid in vocal range (not just sub-bass rumble)
        vocal_threshold = 0.08  # tuned for browser audio levels
        centroid_in_vocal_range = 300.0 < spectral_centroid < 5000.0
        self.state.vocal_present = vocal_e > vocal_threshold and centroid_in_vocal_range
        self.state.vocal_energy = vocal_e

        # Vocal rhythm: rate of change in vocal energy (syllabic rhythm)
        de = abs(vocal_e - self._prev_vocal_energy)
        self._vocal_rhythm_history.append(de)
        avg_rhythm = sum(self._vocal_rhythm_history) / max(1, len(self._vocal_rhythm_history))
        self.state.vocal_rhythm = min(1.0, avg_rhythm * 15.0)  # scale up
        self._prev_vocal_energy = vocal_e

        # Pitch trend (from spectral centroid movement)
        self._vocal_pitch_history.append(spectral_centroid)
        if len(self._vocal_pitch_history) >= 5:
            recent = list(self._vocal_pitch_history)
            # Linear trend over last ~5 frames
            trend = recent[-1] - recent[-5]
            self.state.vocal_pitch_rising = trend > 100.0   # centroid rising
            self.state.vocal_pitch_falling = trend < -100.0  # centroid falling
        else:
            self.state.vocal_pitch_rising = False
            self.state.vocal_pitch_falling = False

        # Vocal sustain: inverse of onset density in vocal range
        # High sustain = legato singing, low sustain = staccato/rap
        self._vocal_onset_history.append(onset_envelope)
        onset_density = sum(1 for o in self._vocal_onset_history if o > 0.02) / max(1, len(self._vocal_onset_history))
        self.state.vocal_sustain = max(0.0, min(1.0, 1.0 - onset_density * 2.0))

        # Cadence phase: extract dominant rhythm from vocal energy changes
        if len(self._vocal_rhythm_history) >= 10:
            rhythm_vals = list(self._vocal_rhythm_history)[-20:]
            # Simple zero-crossing rate as rhythm phase proxy
            crossings = sum(1 for i in range(1, len(rhythm_vals))
                          if (rhythm_vals[i] > avg_rhythm) != (rhythm_vals[i-1] > avg_rhythm))
            self.state.vocal_cadence_phase = (crossings / max(1, len(rhythm_vals))) * 2.0
            self.state.vocal_cadence_phase = min(1.0, self.state.vocal_cadence_phase)

        # ── Ethereal detection ──
        # Ethereal = low bass + high sustain + sparse onsets + high-ish centroid
        # Think: sustained synth pads, airy vocals, reverb tails
        self._onset_density_history.append(1.0 if onset_envelope > 0.02 else 0.0)
        sparse_onsets = (sum(self._onset_density_history) / max(1, len(self._onset_density_history))) < 0.25
        low_bass = bass < 0.15
        high_sustain = self.state.vocal_sustain > 0.6
        airy_centroid = spectral_centroid > 1500.0
        low_energy = energy < 0.35

        ethereal_score = (
            0.25 * (1.0 if sparse_onsets else 0.0) +
            0.25 * (1.0 if low_bass else 0.0) +
            0.20 * (1.0 if high_sustain else 0.0) +
            0.15 * (1.0 if airy_centroid else 0.0) +
            0.15 * (1.0 if low_energy else 0.0)
        )
        self._ethereal_score_history.append(ethereal_score)
        avg_ethereal = sum(self._ethereal_score_history) / max(1, len(self._ethereal_score_history))

        self.state.ethereal_intensity = avg_ethereal
        self.state.is_ethereal = avg_ethereal > 0.55  # need consistent ethereal character

    # ══════════════════════════════════════════════════════════════════
    #  LAYER 2: LYRIC TRANSCRIPTION (Whisper, every ~3-5 seconds)
    # ══════════════════════════════════════════════════════════════════

    def feed_audio(self, audio_chunk: np.ndarray):
        """Feed audio samples into the rolling buffer for Whisper transcription.

        Call this every audio chunk. The actual transcription happens
        asynchronously on a timer.
        """
        self._audio_buffer.extend(audio_chunk.tolist())

    async def maybe_transcribe(self, current_time: float) -> Optional[str]:
        """Run Whisper transcription if enough time has passed.

        Returns transcription text if run, None if skipped.
        Should be called from the main audio processing loop.
        """
        if not self._whisper_available or self._whisper_model is None:
            return None

        if (current_time - self._last_transcription_time) < self._transcription_interval:
            return None

        # Get the last 3-5 seconds of audio
        buffer_samples = list(self._audio_buffer)
        if len(buffer_samples) < self.sample_rate * 2:  # need at least 2 seconds
            return None

        self._last_transcription_time = current_time

        try:
            # Convert to numpy array for Whisper
            audio_array = np.array(buffer_samples[-self.sample_rate * 4:], dtype=np.float32)

            # Run Whisper (this is the expensive part)
            # Use fp16=False for CPU, True for GPU
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._whisper_model.transcribe(
                    audio_array,
                    language="en",
                    fp16=False,
                    no_speech_threshold=0.6,
                    condition_on_previous_text=False,
                )
            )

            text = result.get("text", "").strip().lower()
            if text and len(text) > 2:
                self.state.last_transcription = text
                self.state.last_transcription_time = current_time
                self._transcription_history.append(text)
                logger.debug(f"Whisper transcription: '{text}'")

                # Match keywords to theme
                self._match_lyric_theme(text, current_time)
                return text

        except Exception as e:
            logger.warning(f"Whisper transcription error: {e}")

        return None

    def _match_lyric_theme(self, text: str, current_time: float):
        """Match transcribed text against keyword themes.

        Uses a weighted scoring system: more keyword matches = higher confidence.
        Themes with higher priority are checked first.
        """
        text_lower = text.lower()

        # Don't change theme if current one is still in hold period
        if current_time < self.state.theme_hold_until and self._active_theme_obj is not None:
            # But update confidence if we find more matches for current theme
            current_matches = sum(1 for kw in self._active_theme_obj.keywords if kw in text_lower)
            if current_matches > 0:
                self.state.theme_confidence = min(1.0, self.state.theme_confidence + 0.1)
                self.state.theme_hold_until = current_time + self._theme_hold_duration
            return

        # Score each theme
        best_theme = None
        best_score = 0.0

        # Sort themes by priority (highest first)
        sorted_themes = sorted(LYRIC_THEMES, key=lambda t: t.priority, reverse=True)

        for theme in sorted_themes:
            score = 0.0
            matches = 0
            for keyword in theme.keywords:
                if keyword in text_lower:
                    matches += 1
                    # Longer keywords are more specific, weight them higher
                    score += 1.0 + len(keyword) * 0.1

            # Also check recent transcription history for theme persistence
            history_text = " ".join(list(self._transcription_history)[-3:]).lower()
            for keyword in theme.keywords:
                if keyword in history_text:
                    score += 0.3  # bonus for persistence

            # Weight by priority: higher priority themes win ties
            weighted_score = score + theme.priority * 0.15
            if weighted_score > best_score and matches >= 1:
                best_score = weighted_score
                best_theme = theme

        if best_theme is not None and best_score > 0.8:
            self._active_theme_obj = best_theme
            self.state.active_theme = best_theme.name
            self.state.theme_confidence = min(1.0, best_score / 5.0)
            self.state.theme_dominant = best_theme.dominant
            self.state.theme_accent = best_theme.accent
            self.state.theme_warmth = best_theme.warmth
            self.state.theme_energy = best_theme.energy
            self.state.theme_mood = best_theme.mood
            self.state.theme_hold_until = current_time + self._theme_hold_duration
            logger.info(
                f"Lyric theme matched: {best_theme.name} "
                f"(confidence={self.state.theme_confidence:.2f}, "
                f"mood={best_theme.mood})"
            )
        elif current_time > self.state.theme_hold_until:
            # Theme expired, clear it (will fall back to spectral centroid colors)
            self._active_theme_obj = None
            self.state.active_theme = None
            self.state.theme_confidence *= 0.9  # fade out gradually

    def get_movement_modulation(self) -> Dict[str, float]:
        """Get movement modulation values from vocal cadence.

        Returns a dict of modifiers that the effects engine can apply
        to its movement layer.
        """
        mod = {
            "bounce_intensity": 0.0,   # 0-1: how much to add bounce to movements
            "tilt_accent": 0.0,        # 0-1: accent tilt on vocal hits
            "speed_modifier": 1.0,     # multiplier on movement speed
            "amplitude_modifier": 1.0, # multiplier on movement amplitude
            "ethereal_slowdown": 1.0,  # speed reduction for ethereal moments
        }

        if self.state.vocal_present:
            # Vocal rhythm → bounce intensity
            # When vocal has strong cadence, add bounce to movement
            mod["bounce_intensity"] = self.state.vocal_rhythm * 0.6

            # Vocal pitch rising → tilt accent (fixtures look up with rising melody)
            if self.state.vocal_pitch_rising:
                mod["tilt_accent"] = 0.3
            elif self.state.vocal_pitch_falling:
                mod["tilt_accent"] = -0.2

            # High sustain (legato singing) → slower, wider movements
            if self.state.vocal_sustain > 0.5:
                mod["speed_modifier"] = 0.7 + 0.3 * (1.0 - self.state.vocal_sustain)
                mod["amplitude_modifier"] = 1.0 + 0.3 * self.state.vocal_sustain

        # Ethereal: VERY slow, VERY wide (fly-outs)
        if self.state.is_ethereal:
            ethereal_strength = self.state.ethereal_intensity
            mod["ethereal_slowdown"] = max(0.2, 1.0 - ethereal_strength * 0.8)
            mod["speed_modifier"] *= mod["ethereal_slowdown"]
            mod["amplitude_modifier"] *= 1.0 + ethereal_strength * 0.5  # wider

        return mod

    def get_color_theme(self) -> Optional[Dict[str, Any]]:
        """Get the current lyric-driven color theme, if active.

        Returns None if no lyric theme is active (fall back to spectral centroid).
        """
        if self.state.active_theme is None or self.state.theme_confidence < 0.2:
            return None

        return {
            "name": self.state.active_theme,
            "mood": self.state.theme_mood,
            "dominant": self.state.theme_dominant,
            "accent": self.state.theme_accent,
            "warmth": self.state.theme_warmth,
            "energy": self.state.theme_energy,
            "confidence": self.state.theme_confidence,
            "is_ethereal": self.state.is_ethereal,
            "ethereal_intensity": self.state.ethereal_intensity,
        }
