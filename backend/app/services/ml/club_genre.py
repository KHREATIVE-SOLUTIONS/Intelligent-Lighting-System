"""
Club Genre Model
================

A trained genre and mood tagger for the live feed, in place of the spectral
heuristic (which calls club music "ambient" and is ignored by the show).

The model is EfficientAT's `mn10_as` (MIT licence, vendored in `efficientat/`):
a 4.9M-parameter MobileNet trained on AudioSet, 0.5 GMACs per 10 s of audio,
comfortably real time on a venue box's CPU. AudioSet tags House, Techno, Drum
and bass, Dubstep, Trance, Hip hop, Latin, Afrobeat, Pop, Disco, Funk and more,
plus six mood classes; those tags are folded into the handful of club styles
the lighting knows how to lean towards.

Off unless `GENRE_MODEL_ENABLED` is set and the checkpoint has been fetched
with `scripts/download_genre_model.py`. Nothing here downloads at run time.

What the style is allowed to change is decided by the effects engine: palette
and movement character only. Energy and sections still run the show.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from app.services.ml.genre_classifier import GenreResult

logger = logging.getLogger(__name__)

MODEL_SAMPLE_RATE = 32000

# AudioSet class indices (class_labels_indices.csv) behind each club style. A
# style scores as its strongest member.
STYLE_CLASSES: Dict[str, Tuple[int, ...]] = {
    "house": (240,),                       # House music
    "techno": (241,),                      # Techno
    "dnb": (243, 242),                     # Drum and bass, Dubstep
    "trance": (247,),                      # Trance music
    "edm": (239, 244, 245, 274),           # Electronic, Electronica, EDM, Dance music
    "hip_hop": (217, 226),                 # Hip hop, Rhythm and blues
    "latin": (248, 249, 250),              # Latin America, Salsa, Flamenco
    "afro": (256, 257, 228, 263),          # Music of Africa, Afrobeat, Reggae, Ska
    "open_format": (216, 236, 232, 227),   # Pop, Disco, Funk, Soul
    "rock": (219, 220, 221, 224),          # Rock, Heavy metal, Punk, Rock and roll
    "lounge": (235, 237, 246, 253),        # Jazz, Classical, Ambient, New-age
}
ELECTRONIC_STYLES = ("house", "techno", "dnb", "trance", "edm")
SPECIFIC_ELECTRONIC = ("house", "techno", "dnb", "trance")

MUSIC_CLASS = 137
# (valence, arousal) each mood class pulls towards.
MOOD_CLASSES: Dict[int, Tuple[str, float, float]] = {
    276: ("happy", 0.7, 0.4),
    278: ("sad", -0.7, -0.5),
    279: ("tender", 0.4, -0.6),
    280: ("exciting", 0.4, 0.8),
    281: ("angry", -0.6, 0.8),
    282: ("scary", -0.7, 0.5),
}

# Below this the window is not music (talk, a room, a test tone) and no style
# is named. AudioSet's "Music" fires near 1.0 on any track.
MIN_MUSIC = 0.3
# A style has to stand out this much before it is named at all.
MIN_STYLE_SCORE = 0.08
# Generic "Electronic" gives way to a named electronic style scoring at least
# this share of it: a house record tags both, and "house" is the useful answer.
SPECIFIC_OVER_GENERIC = 0.5


def style_scores(probs: np.ndarray) -> Dict[str, float]:
    return {style: float(max(probs[i] for i in idx)) for style, idx in STYLE_CLASSES.items()}


def pick_style(scores: Dict[str, float], music: float) -> Tuple[str, float]:
    """(style, confidence) from the style scores; ("unknown", 0.0) when unsure.

    Confidence is how clearly the style beats its nearest rival, top / (top +
    runner-up), so it reads the same on a quiet tag and a loud one. A named
    electronic style does not count generic "Electronic" as a rival, since a
    house record carries both tags.
    """
    if music < MIN_MUSIC:
        return "unknown", 0.0
    style = max(scores, key=scores.get)
    if scores[style] < MIN_STYLE_SCORE:
        return "unknown", 0.0
    if style == "edm":
        specific = max(SPECIFIC_ELECTRONIC, key=lambda s: scores[s])
        if scores[specific] >= SPECIFIC_OVER_GENERIC * scores["edm"]:
            style = specific
    rivals = [
        v for k, v in scores.items()
        if k != style and not (style in SPECIFIC_ELECTRONIC and k == "edm")
    ]
    top = scores[style]
    runner_up = max(rivals) if rivals else 0.0
    return style, float(top / (top + runner_up))


def mood_from_probs(probs: np.ndarray) -> Dict[str, float]:
    weights = {i: float(probs[i]) for i in MOOD_CLASSES}
    total = sum(weights.values())
    if total <= 0:
        return {"label": "unknown", "valence": 0.0, "arousal": 0.0}
    valence = sum(w * MOOD_CLASSES[i][1] for i, w in weights.items()) / total
    arousal = sum(w * MOOD_CLASSES[i][2] for i, w in weights.items()) / total
    label = MOOD_CLASSES[max(weights, key=weights.get)][0]
    return {"label": label, "valence": round(valence, 3), "arousal": round(arousal, 3)}


class ClubGenreModel:
    """Live club-style tagger. Same `classify` contract as `GenreClassifier`."""

    HEURISTIC_ONLY = False
    WINDOW_S = 10.0
    # The analyser asks this often; the result is smoothed across windows, so a
    # style is named after about three agreeing looks rather than one.
    interval_s = 5.0
    MIN_WINDOW_S = 3.0
    SMOOTHING = 0.5

    def __init__(self, weights_path, device: str = "cpu"):
        self.weights_path = Path(weights_path)
        self.device = device
        self.loaded = False
        self._model = None
        self._frontend = None
        self._buffer = np.zeros(0, dtype=np.float32)
        self._buffer_rate = 0
        self._smoothed: Optional[np.ndarray] = None
        self.last_mood: Optional[Dict[str, float]] = None
        self.last_inference_ms = 0.0

    async def load(self):
        await asyncio.to_thread(self._load_sync)

    def _load_sync(self):
        if not self.weights_path.is_file():
            raise FileNotFoundError(
                f"genre model weights not found at {self.weights_path}; "
                "run scripts/download_genre_model.py"
            )
        import torch

        from app.services.ml.efficientat import MelFrontend, build_mn

        device = self.device
        if device.startswith("cuda") and not torch.cuda.is_available():
            logger.warning("Genre model asked for %s but no CUDA device is present; using CPU", device)
            device = "cpu"
        model = build_mn()
        state = torch.load(self.weights_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state, strict=True)
        model.eval().to(device)
        frontend = MelFrontend().eval().to(device)
        self._model, self._frontend, self.device = model, frontend, device
        self.loaded = True
        logger.info("Club genre model loaded from %s on %s", self.weights_path, device)

    def feed_audio(self, audio: np.ndarray, sample_rate: int):
        """Keep the last WINDOW_S of the feed at its own rate."""
        rate = int(sample_rate)
        if rate != self._buffer_rate:
            self._buffer = np.zeros(0, dtype=np.float32)
            self._buffer_rate = rate
        chunk = np.asarray(audio, dtype=np.float32).reshape(-1)
        keep = int(self.WINDOW_S * rate)
        self._buffer = np.concatenate([self._buffer, chunk])[-keep:]

    def reset(self):
        """Forget the smoothing, e.g. when the operator says it is a new set."""
        self._smoothed = None

    async def classify(self, audio_buffer=None, sample_rate=None) -> Optional[GenreResult]:
        """Name the style of the last window. None until a window has filled.

        The analyser's own 4 s buffer is used only when nothing was fed here.
        """
        if not self.loaded:
            return None
        if self._buffer_rate and len(self._buffer) >= self.MIN_WINDOW_S * self._buffer_rate:
            window, rate = self._buffer.copy(), self._buffer_rate
        elif audio_buffer is not None and sample_rate:
            window, rate = np.asarray(audio_buffer, dtype=np.float32).copy(), int(sample_rate)
        else:
            return None
        return await asyncio.to_thread(self._classify_sync, window, rate)

    def _probs(self, window: np.ndarray, rate: int) -> np.ndarray:
        import torch
        from scipy.signal import resample_poly

        if rate != MODEL_SAMPLE_RATE:
            g = np.gcd(int(rate), MODEL_SAMPLE_RATE)
            window = resample_poly(window, MODEL_SAMPLE_RATE // g, int(rate) // g).astype(np.float32)
        x = torch.from_numpy(np.ascontiguousarray(window, dtype=np.float32))[None].to(self.device)
        with torch.inference_mode():
            logits = self._model(self._frontend(x).unsqueeze(1))
        return torch.sigmoid(logits.float()).squeeze(0).cpu().numpy()

    def _classify_sync(self, window: np.ndarray, rate: int) -> GenreResult:
        started = time.perf_counter()
        window = np.nan_to_num(window, nan=0.0, posinf=0.0, neginf=0.0)
        if float(np.sqrt(np.mean(window ** 2))) < 1e-4:
            # Silence says nothing about the style: keep what was learned.
            return GenreResult(genre="unknown", timestamp=time.time())

        probs = self._probs(window, rate)
        if self._smoothed is None:
            self._smoothed = probs
        else:
            self._smoothed = self.SMOOTHING * probs + (1.0 - self.SMOOTHING) * self._smoothed
        smoothed = self._smoothed

        scores = style_scores(smoothed)
        music = float(smoothed[MUSIC_CLASS])
        style, confidence = pick_style(scores, music)
        self.last_mood = mood_from_probs(smoothed) if music >= MIN_MUSIC else None
        self.last_inference_ms = (time.perf_counter() - started) * 1000.0

        if style == "unknown":
            top = "unknown"
        else:
            top = "electronic" if style in ELECTRONIC_STYLES else "mixed"
        return GenreResult(
            top_level=top,
            top_level_confidence=confidence,
            genre=style,
            genre_confidence=confidence,
            subgenre=style,
            subgenre_confidence=confidence,
            genre_scores={k: round(v, 4) for k, v in scores.items()},
            timestamp=time.time(),
        )

    def get_info(self) -> Dict[str, object]:
        return {
            "model": "EfficientAT mn10_as (AudioSet, MIT)",
            "loaded": self.loaded,
            "device": self.device,
            "weights": str(self.weights_path),
            "last_inference_ms": round(self.last_inference_ms, 1),
            "styles": list(STYLE_CLASSES),
        }
