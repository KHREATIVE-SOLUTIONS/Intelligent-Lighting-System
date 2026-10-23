"""
Track Change Detection
======================

Notices when a DJ has mixed into a new track, without waiting for silence.

The engine used to start a new song only after 1.5 s of silence, and a DJ mix
never goes silent, so a whole set read as one six-hour song: one palette, one
set of section statistics, one drop history. This listens for the two things
that do change at a track boundary even when the mix is seamless:

- **Harmony.** Each record keeps to its own key. The track's harmonic profile
  is the average 12-bin chroma of everything heard since it started; the last
  `WINDOW_S` is compared with it by the correlation of their log chroma. A
  breakdown or a chorus in the same key stays close to the track's profile; the
  incoming record's key does not.
- **Tempo.** A confident tempo that moves by more than `TEMPO_JUMP` and stays
  there is a new record, not a fill. Beatmatched mixes keep the tempo, which is
  why harmony is the main cue.

The profile only learns from material that already agrees with it, so the slow
crossfade of a blend cannot drag it across to the incoming key. A change is
called once the new harmony has held for `CONFIRM_S`, and the profile restarts
from what was heard while confirming. Drum-only passages carry no harmony and
neither confirm nor cancel anything.

Measured on generated material (chord stabs over drums, beatmatched
equal-power crossfades): a mix from A minor into E flat major is called within
a second of the end of a 16-bar blend and a few seconds before the end of a
32-bar one; a same-key chorus with a borrowed chord peaks at 0.49 against the
0.65 threshold, and steady material stays under 0.04. None of the harness's
single-track material registers a change. Not yet validated on recorded DJ
sets, where chroma is less clean.

Published state, read by the analyser:

- `track_id`: increments once per detected change, starting at 0.
- `transition`: 0..1, how far the current material is towards "this is a
  different record"; 1 on the update a change is confirmed.
- `changed`: true on the one update where `track_id` moved.

Two records in the same key with similar chords, mixed at the same tempo, read
as one record, which is no worse than before.
"""

from collections import deque
from typing import Deque, List, Optional

import numpy as np


class TrackChangeDetector:
    """Streaming harmonic and tempo novelty against the current track's profile."""

    FFT_SIZE = 4096
    FMIN = 110.0               # A2: below this a 4096-point FFT cannot split semitones
    FMAX = 2100.0
    UPDATE_S = 1.0
    WINDOW_S = 8.0             # recent harmony
    ESTABLISH_S = 16.0         # profile needed before anything is compared with it
    LOG_FLOOR = 0.02           # keeps near-empty pitch classes from dominating
    NOVELTY_ON = 0.65          # a different key
    NOVELTY_LEARN = 0.30       # the profile only learns below this
    CONFIRM_S = 4.0
    MIN_TRACK_S = 30.0         # no change is called sooner than this after the last
    # A window flatter than this has no usable harmony (drums, noise, silence).
    MIN_TONALITY = 0.35
    SILENCE_RMS = 0.003
    TEMPO_JUMP = 0.04
    TEMPO_MIN_CONFIDENCE = 0.5

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = int(sample_rate)
        self._build_pitch_map()
        self.reset()

    def set_sample_rate(self, sample_rate: int) -> None:
        sample_rate = int(sample_rate)
        if sample_rate > 0 and sample_rate != self.sample_rate:
            self.sample_rate = sample_rate
            self._build_pitch_map()
            self.reset()

    def _build_pitch_map(self) -> None:
        freqs = np.fft.rfftfreq(self.FFT_SIZE, 1.0 / self.sample_rate)
        band = (freqs >= self.FMIN) & (freqs <= self.FMAX)
        self._bins = np.nonzero(band)[0]
        midi = 69.0 + 12.0 * np.log2(freqs[self._bins] / 440.0)
        self._pitch_class = np.mod(np.rint(midi).astype(int), 12)
        self._window = np.hanning(self.FFT_SIZE).astype(np.float32)

    def reset(self) -> None:
        self._buffer = np.zeros(self.FFT_SIZE, dtype=np.float32)
        self._acc = np.zeros(12)
        self._acc_frames = 0
        self._acc_seconds = 0.0
        self._seconds = 0.0
        self._recent: Deque[np.ndarray] = deque(maxlen=int(round(self.WINDOW_S / self.UPDATE_S)))
        self._profile_sum = np.zeros(12)
        self._profile_seconds = 0.0
        self._track_start = 0.0
        self._novel_since: Optional[float] = None
        self._pending: List[np.ndarray] = []
        self._tempo_ref: Optional[float] = None
        self._tempo_new: Optional[float] = None
        self._tempo_new_since: Optional[float] = None

        self.track_id = 0
        self.transition = 0.0
        self.changed = False
        self.novelty = 0.0

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def push(self, samples: np.ndarray, bpm: Optional[float] = None,
             tempo_confidence: float = 0.0) -> bool:
        """Feed one block. Returns True when the published state was updated."""
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        self.changed = False
        if x.size == 0:
            return False
        if x.size >= self.FFT_SIZE:
            self._buffer = x[-self.FFT_SIZE:].copy()
        else:
            self._buffer = np.concatenate([self._buffer[x.size:], x])

        seconds = x.size / float(self.sample_rate)
        self._seconds += seconds
        self._acc_seconds += seconds
        if float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) >= self.SILENCE_RMS:
            self._acc += self._chroma_frame()
            self._acc_frames += 1

        if self._acc_seconds < self.UPDATE_S:
            return False
        self._acc_seconds -= self.UPDATE_S
        frame = self._acc / self._acc_frames if self._acc_frames else None
        self._acc = np.zeros(12)
        self._acc_frames = 0
        self._update(frame, bpm, tempo_confidence)
        return True

    def _chroma_frame(self) -> np.ndarray:
        spectrum = np.abs(np.fft.rfft(self._buffer * self._window))[self._bins]
        power = spectrum.astype(np.float64) ** 2
        chroma = np.bincount(self._pitch_class, weights=power, minlength=12)
        total = chroma.sum()
        return chroma / total if total > 0 else np.zeros(12)

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    @staticmethod
    def _tonality(profile: np.ndarray) -> float:
        """0 for a flat profile, 1 for a single pitch class."""
        peak = float(profile.max())
        if peak <= 0.0:
            return 0.0
        return max(0.0, (peak - float(profile.mean())) / peak)

    @classmethod
    def _distance(cls, a: np.ndarray, b: np.ndarray) -> float:
        """1 minus the correlation of the two log chroma profiles (0..2)."""
        la = np.log(a / max(float(a.sum()), 1e-12) + cls.LOG_FLOOR)
        lb = np.log(b / max(float(b.sum()), 1e-12) + cls.LOG_FLOOR)
        la -= la.mean()
        lb -= lb.mean()
        na, nb = float(np.linalg.norm(la)), float(np.linalg.norm(lb))
        if na <= 0.0 or nb <= 0.0:
            return 1.0
        return 1.0 - float(np.dot(la, lb)) / (na * nb)

    def _learn(self, profile: np.ndarray) -> None:
        self._profile_sum += profile
        self._profile_seconds += self.UPDATE_S

    def _update(self, frame: Optional[np.ndarray], bpm: Optional[float], tempo_confidence: float) -> None:
        now = self._seconds
        if frame is not None:
            self._recent.append(frame)
        window = np.mean(self._recent, axis=0) if self._recent else None
        tonal = (
            window is not None
            and len(self._recent) >= self._recent.maxlen // 2
            and self._tonality(window) >= self.MIN_TONALITY
        )
        settled = (now - self._track_start) >= self.MIN_TRACK_S
        tempo_jumped = self._tempo_jumped(now, bpm, tempo_confidence)

        if tempo_jumped and settled:
            self._confirm(now, window if tonal else None)
            return

        if not tonal:
            # Nothing to compare. An in-flight transition decays rather than
            # snapping back, so a drum-only bar in a blend does not restart it.
            self.novelty = 0.0
            if self._novel_since is not None:
                self.transition = max(0.0, self.transition - self.UPDATE_S / self.CONFIRM_S)
                if self.transition <= 0.0:
                    self._novel_since = None
                    self._pending = []
            return

        if self._profile_seconds < self.ESTABLISH_S:
            self._learn(window)
            self.novelty = 0.0
            self.transition = 0.0
            return

        self.novelty = self._distance(window, self._profile_sum)

        if self.novelty >= self.NOVELTY_ON and settled:
            if self._novel_since is None:
                self._novel_since = now
                self._pending = []
            self._pending.append(window)
            held = now - self._novel_since
            self.transition = min(1.0, held / self.CONFIRM_S)
            if held >= self.CONFIRM_S:
                self._confirm(now, window)
            return

        # Back inside the track's own material.
        self._novel_since = None
        self._pending = []
        self.transition = 0.0
        if self.novelty < self.NOVELTY_LEARN:
            self._learn(window)

    def _tempo_jumped(self, now: float, bpm: Optional[float], confidence: float) -> bool:
        try:
            bpm = float(bpm) if bpm is not None else None
            confidence = float(confidence or 0.0)
        except (TypeError, ValueError):
            return False
        if bpm is None or not (40.0 <= bpm <= 260.0) or confidence < self.TEMPO_MIN_CONFIDENCE:
            self._tempo_new = None
            self._tempo_new_since = None
            return False
        if self._tempo_ref is None:
            self._tempo_ref = bpm
            return False
        if abs(bpm / self._tempo_ref - 1.0) <= self.TEMPO_JUMP:
            self._tempo_ref += (bpm - self._tempo_ref) * 0.2
            self._tempo_new = None
            self._tempo_new_since = None
            return False
        if self._tempo_new is None or abs(bpm / self._tempo_new - 1.0) > self.TEMPO_JUMP:
            self._tempo_new = bpm
            self._tempo_new_since = now
            return False
        return (now - self._tempo_new_since) >= self.CONFIRM_S

    def _confirm(self, now: float, window: Optional[np.ndarray]) -> None:
        self.track_id += 1
        self.changed = True
        self.transition = 1.0
        heard = list(self._pending)
        if window is not None:
            heard.append(window)
        self._profile_sum = np.sum(heard, axis=0) if heard else np.zeros(12)
        self._profile_seconds = len(heard) * self.UPDATE_S
        self._pending = []
        self._novel_since = None
        self._track_start = now
        if self._tempo_new is not None:
            self._tempo_ref = self._tempo_new
        self._tempo_new = None
        self._tempo_new_since = None
