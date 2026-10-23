"""
Genre Night Check
=================

How the club genre model is checked on real nights before it is allowed to
steer a show. The operator starts a check at the start of a gig; every answer
the model gives is written to a log, with a short clip of the audio it heard
now and then, and the operator taps what is actually playing whenever it
changes. Afterwards the log is scored: how often the model named the style the
operator marked, and how often the show would have been in the right style
under the engine's own adoption rule.

During a check the model only listens unless GENRE_MODEL_ENABLED is set, so a
wrong guess costs nothing on the night.

A night lives in `<data_dir>/genre_check/<started>/`: `log.jsonl` (one JSON
object per line, kind "guess", "mark", "start" or "stop") and `clips/`, 16 kHz
mono WAVs named by the second they end on. Clips are the house feed the box is
already analysing, kept on the box and never sent anywhere.
"""

import json
import logging
import threading
import time
import wave
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.services.ml.club_genre import STYLE_CLASSES

logger = logging.getLogger(__name__)

# What the operator can mark: every style the model can name, plus music that
# fits none of them and anything that is not music (talk, a set change).
MARKS = tuple(STYLE_CLASSES) + ("other", "not_music")
CLIP_RATE = 16000
CLIP_EVERY_S = 60.0
# A mark can be backdated this far, for a change noticed a little late.
MAX_BACKDATE_S = 600.0

# The engine's adoption rule (effects_engine._CLUB_STYLE_*), restated so a log
# can be scored without an engine. The tests hold the two together.
ADOPT_MIN_CONFIDENCE = 0.55
ADOPT_VOTES = 3


def _root(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from app.core.config import settings

        data_dir = settings.data_dir
    return Path(data_dir) / "genre_check"


class GenreNightCheck:
    """One night's log. Thread-safe: guesses are written from a worker thread."""

    def __init__(self, data_dir: Optional[Path] = None, clip_every_s: float = CLIP_EVERY_S):
        self.root = _root(data_dir)
        self.clip_every_s = float(clip_every_s)
        self.night: Optional[str] = None
        self.steering = False
        self._lock = threading.Lock()
        self._last_clip_t = -1e9
        self.guesses = 0
        self.marks = 0
        self.last_guess: Optional[Dict] = None
        self.current_mark: Optional[Dict] = None

    @property
    def active(self) -> bool:
        return self.night is not None

    @property
    def path(self) -> Optional[Path]:
        return self.root / self.night if self.night else None

    def start(self, steering: bool = False, now: Optional[float] = None) -> str:
        """Open a new night. Starting while one is open keeps that one."""
        if self.active:
            return self.night
        now = time.time() if now is None else now
        night = datetime.fromtimestamp(now).strftime("%Y-%m-%d_%H%M%S")
        (self.root / night / "clips").mkdir(parents=True, exist_ok=True)
        self.night = night
        self.steering = bool(steering)
        self.guesses = self.marks = 0
        self.last_guess = self.current_mark = None
        self._last_clip_t = -1e9
        self._write({"t": now, "kind": "start", "steering": self.steering})
        return night

    def stop(self, now: Optional[float] = None) -> Optional[str]:
        if not self.active:
            return None
        self._write({"t": time.time() if now is None else now, "kind": "stop"})
        night, self.night = self.night, None
        return night

    def mark(self, style: str, since_s: float = 0.0, now: Optional[float] = None) -> Dict:
        """The operator says what is playing, from `since_s` seconds ago."""
        if not self.active:
            raise RuntimeError("no night check is running")
        if style not in MARKS:
            raise ValueError(f"unknown style {style!r}")
        since_s = max(0.0, min(MAX_BACKDATE_S, float(since_s)))
        now = time.time() if now is None else now
        entry = {"t": now - since_s, "kind": "mark", "style": style}
        self._write(entry)
        self.marks += 1
        self.current_mark = entry
        return entry

    def record(self, result, mood: Optional[Dict] = None, window: Optional[np.ndarray] = None,
               rate: Optional[int] = None, now: Optional[float] = None) -> Optional[Dict]:
        """Log one model answer, and a clip of what it heard when one is due."""
        if not self.active or result is None:
            return None
        now = time.time() if now is None else now
        entry = {
            "t": now,
            "kind": "guess",
            "style": getattr(result, "genre", "unknown"),
            "confidence": round(float(getattr(result, "genre_confidence", 0.0) or 0.0), 4),
            "scores": dict(getattr(result, "genre_scores", {}) or {}),
            "mood": mood,
        }
        if window is not None and rate and now - self._last_clip_t >= self.clip_every_s:
            name = self._save_clip(window, int(rate), now)
            if name:
                entry["clip"] = name
                self._last_clip_t = now
        self._write(entry)
        self.guesses += 1
        self.last_guess = entry
        return entry

    def status(self) -> Dict:
        return {
            "active": self.active,
            "night": self.night,
            "steering": self.steering,
            "guesses": self.guesses,
            "marks": self.marks,
            "last_guess": self.last_guess,
            "current_mark": self.current_mark,
            "styles": list(MARKS),
        }

    def _write(self, entry: Dict) -> None:
        path = self.path
        if path is None:
            return
        line = json.dumps(entry, separators=(",", ":"))
        with self._lock:
            try:
                with open(path / "log.jsonl", "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as e:
                logger.warning("Genre night check could not write its log: %s", e)

    def _save_clip(self, window: np.ndarray, rate: int, now: float) -> Optional[str]:
        try:
            from scipy.signal import resample_poly

            audio = np.nan_to_num(np.asarray(window, dtype=np.float32).reshape(-1))
            if rate != CLIP_RATE:
                g = np.gcd(rate, CLIP_RATE)
                audio = resample_poly(audio, CLIP_RATE // g, rate // g)
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
            name = f"{datetime.fromtimestamp(now).strftime('%H%M%S')}.wav"
            with wave.open(str(self.path / "clips" / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(CLIP_RATE)
                w.writeframes(pcm.tobytes())
            return name
        except Exception as e:
            logger.warning("Genre night check could not save a clip: %s", e)
            return None


def list_nights(data_dir: Optional[Path] = None) -> List[str]:
    root = _root(data_dir)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "log.jsonl").is_file())


def read_log(night_dir: Path) -> List[Dict]:
    entries = []
    with open(Path(night_dir) / "log.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue  # a line cut short by a power cut
    return sorted(entries, key=lambda e: e.get("t", 0.0))


def score(entries: List[Dict]) -> Dict:
    """How the model did against the operator's marks.

    Each guess is judged against the latest mark at or before it; guesses
    before the first mark, or under an "other" or "not_music" mark, are counted
    but not judged. `accuracy` is over every judged guess, `confident_accuracy`
    over the ones confident enough to count as a vote, and `show_accuracy` is
    what matters on the night: the style the engine would have been showing,
    under its own three-vote rule, against what was marked.
    """
    current_mark = None
    adopted = None
    candidate, votes = None, 0
    judged = right = 0
    confident = confident_right = 0
    show_judged = show_right = 0
    unmarked = 0
    by_style: Dict[str, Counter] = {}
    confusion: Counter = Counter()

    for e in entries:
        kind = e.get("kind")
        if kind == "mark":
            current_mark = e.get("style")
            continue
        if kind != "guess":
            continue

        style = e.get("style", "unknown")
        conf = float(e.get("confidence") or 0.0)
        # The engine's rule: unsure answers reset the count but keep the style.
        if style not in STYLE_CLASSES or conf < ADOPT_MIN_CONFIDENCE or style == adopted:
            candidate, votes = None, 0
        elif style == candidate:
            votes += 1
        else:
            candidate, votes = style, 1
        if candidate is not None and votes >= ADOPT_VOTES:
            adopted, candidate, votes = candidate, None, 0

        if current_mark is None or current_mark not in STYLE_CLASSES:
            unmarked += 1
            continue
        judged += 1
        hit = style == current_mark
        right += hit
        if style in STYLE_CLASSES and conf >= ADOPT_MIN_CONFIDENCE:
            confident += 1
            confident_right += hit
        if adopted is not None:
            show_judged += 1
            show_right += adopted == current_mark
        tally = by_style.setdefault(current_mark, Counter())
        tally["marked"] += 1
        tally["right"] += hit
        if not hit:
            confusion[f"{current_mark} -> {style}"] += 1

    def ratio(a, b):
        return round(a / b, 3) if b else None

    return {
        "guesses": judged + unmarked,
        "judged": judged,
        "not_judged": unmarked,
        "accuracy": ratio(right, judged),
        "confident_guesses": confident,
        "confident_accuracy": ratio(confident_right, confident),
        "show_judged": show_judged,
        "show_accuracy": ratio(show_right, show_judged),
        "by_style": {
            s: {"marked": c["marked"], "right": c["right"], "accuracy": ratio(c["right"], c["marked"])}
            for s, c in sorted(by_style.items())
        },
        "mistakes": dict(confusion.most_common(10)),
    }


def score_night(night: str, data_dir: Optional[Path] = None) -> Dict:
    night_dir = _root(data_dir) / night
    result = score(read_log(night_dir))
    result["night"] = night
    return result
