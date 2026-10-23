"""
Tempo Tracker
=============

Finds the tempo a lighting operator would count, from the audio itself.

The beat detector in `AudioAnalyzer` estimates tempo from the gaps between the
beats it fires, and the engine's clock only ever sees one loudness value per
analysis block. Both are blind to *which* drum is hitting, so both get the
metrical level wrong on anything that is not four-on-the-floor: drum and bass
locks to 3/4 of its tempo, half-time trap to 3/4 or 4/3, hip-hop to double.
Measured on genre-shaped drum patterns before this module existed, median over
the second half of each track:

    ==================  =====  =========  ======
    material            true   analyser   engine
    ==================  =====  =========  ======
    drum and bass        174     1.01x     0.75x
    half-time trap       150     1.34x     0.74x
    half-time            140     1.37x     1.00x
    hip-hop              92      2.00x     2.00x
    four-on-the-floor    128     1.04x     1.00x
    ==================  =====  =========  ======

What separates the levels is the snare. In almost all popular music the snare
lands on the backbeat (beats 2 and 4) or, in half-time, once a bar on beat 3.
So the mid band is periodic at two (or four) beats and *not* at one, which is
true at the real tempo and false at its double, half, and 3/4 neighbours.

Method, every `UPDATE_S` over the last `WINDOW_S` of audio:

1. Log-magnitude spectral flux on overlapping frames (86 frames/s at 44.1 kHz,
   four per analysis block) in three bands: kick, snare/body, hats.
2. The autocorrelation of each band, and of their standardised sum.
3. Every candidate tempo from `MIN_BPM` to `MAX_BPM` is scored as

       prior(bpm) * pulse(L) * (1 + BACKBEAT_GAIN * backbeat(L)) * bar(L) * sub(L)

   where `L` is the beat period in frames and

   - `pulse` is the summed envelope's autocorrelation at `L`;
   - `backbeat` is how much more periodic the mid band is at `2L` than at any
     shorter period (or at `4L` than at `2L`, for half-time);
   - `bar` is how well the whole kit, and the kick alone, repeat at `4L`, which
     is what rules out the 3/4 and 2/3 neighbours;
   - `sub` checks that `L` is a whole number of hat-grid steps (1, 2, 3, 4,
     6 or 8 of them), measured from the hat band's own shortest strong period.

   The prior is the usual log-normal tempo preference. It only decides between
   levels the drums leave genuinely ambiguous: a boom-bap beat at 87 and a
   half-time beat at 174 are the same pattern, and this picks 87.

On 132 generated tracks (sixteen drum styles in eight variations each, from
-12 to +6 dB, with and without bass and chord parts, plus the harness's click,
dense, tempo-change and drop tracks) this lands within 3% of the counted tempo
on all 132, and on 64 of 64 held-out tracks played through it as a stream.
Pad-only and noise-only input publish no tempo at all.

Published tempo changes only when a new estimate wins `SWITCH_UPDATES` updates
in a row, so a fill or a break cannot flip the show into double time.
"""

import math
from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np


class TempoTracker:
    """Streaming multi-band tempo estimator. Feed it audio with `push`."""

    MIN_BPM = 60.0
    MAX_BPM = 200.0
    WINDOW_S = 8.0
    MIN_HISTORY_S = 4.0
    UPDATE_S = 0.5

    # Band edges in Hz. Kick fundamentals, then snare body and crack (the kick's
    # click lands here too, but only at beat rate), then hats and cymbals.
    BANDS: Dict[str, Tuple[float, Optional[float]]] = {
        "low": (30.0, 150.0),
        "mid": (150.0, 5000.0),
        "high": (5000.0, None),
    }

    PRIOR_BPM = 125.0
    PRIOR_WIDTH = 0.45         # natural-log units, about 0.65 of an octave
    BACKBEAT_GAIN = 3.0
    # Share of the score the bar and subdivision checks control; the rest is a
    # floor so material without hats, or without a repeating bar, still scores.
    BAR_WEIGHT = 0.8
    SUBDIVISION_WEIGHT = 0.8
    # Hat grid: searched between these periods, trusted above this correlation.
    TATUM_RANGE_S = (0.06, 0.40)
    TATUM_MIN = 0.3
    TATUM_TOLERANCE = 0.06
    # How readily a beat is that many hat steps long. Hats on the beat itself
    # are less usual than on eighths or sixteenths; six and eight cover a
    # sixteenth-note grid under a half-time beat.
    SUBDIVISIONS = {1: 0.6, 2: 1.0, 3: 0.9, 4: 1.0, 6: 0.5, 8: 0.5}
    GRID_STEP = 1.005          # candidate spacing, 0.5%

    # Same tempo, for hysteresis and for picking the runner-up.
    SAME_TEMPO_RATIO = 1.04
    SWITCH_UPDATES = 3
    SMOOTHING = 0.3
    # A winning score this high counts as a fully clear drum pattern.
    STRONG_SCORE = 0.2
    # Below this the estimate is not published at all. Drum material scores
    # 0.85 or more; a sustained pad or broadband noise peaks around 0.17.
    MIN_CONFIDENCE = 0.35
    # Frames quieter than this (mean log-magnitude) are treated as silence.
    SILENCE_LEVEL = 0.02

    _BLUR = np.array([1.0, 4.0, 6.0, 4.0, 1.0]) / 16.0

    def __init__(self, sample_rate: int = 44100, hop: int = 512, frame: int = 1024):
        self.hop = int(hop)
        self.frame = int(frame)
        self._window = np.hanning(self.frame).astype(np.float32)
        self.sample_rate = 0
        self.set_sample_rate(sample_rate)

    # ------------------------------------------------------------------ setup

    def set_sample_rate(self, sample_rate: int) -> None:
        rate = int(sample_rate)
        if rate <= 0 or rate == self.sample_rate:
            return
        self.sample_rate = rate
        self.fps = rate / float(self.hop)
        freqs = np.fft.rfftfreq(self.frame, 1.0 / rate)
        self._masks = {}
        for name, (low, high) in self.BANDS.items():
            mask = freqs >= low
            if high is not None:
                mask &= freqs < high
            self._masks[name] = mask
        bpm = self.MIN_BPM * np.power(
            self.GRID_STEP,
            np.arange(int(math.log(self.MAX_BPM / self.MIN_BPM) / math.log(self.GRID_STEP)) + 1),
        )
        self._cand_bpm = bpm
        self._cand_lag = self.fps * 60.0 / bpm
        self._prior = np.exp(-0.5 * (np.log(bpm / self.PRIOR_BPM) / self.PRIOR_WIDTH) ** 2)
        self.reset()

    def reset(self) -> None:
        """Forget everything heard so far."""
        size = int(round(self.WINDOW_S * self.fps))
        self._env = {name: deque(maxlen=size) for name in self.BANDS}
        self._frame_buf = np.zeros(self.frame, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._prev_mag: Optional[np.ndarray] = None
        self._frames_since_update = 0
        self._candidate: Optional[float] = None
        self._candidate_wins = 0
        self.bpm: Optional[float] = None
        self.confidence = 0.0
        self.raw_bpm: Optional[float] = None
        self.raw_confidence = 0.0

    # --------------------------------------------------------------- streaming

    def push(self, samples: np.ndarray) -> bool:
        """Add mono samples. Returns True when the estimate was refreshed."""
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        if data.size == 0:
            return False
        if self._pending.size:
            data = np.concatenate([self._pending, data])
        hop = self.hop
        count = data.size // hop
        for i in range(count):
            self._add_hop(data[i * hop:(i + 1) * hop])
        self._pending = data[count * hop:].copy()

        update_every = max(1, int(round(self.UPDATE_S * self.fps)))
        if self._frames_since_update < update_every:
            return False
        self._frames_since_update = 0
        self._update()
        return True

    def _add_hop(self, hop_samples: np.ndarray) -> None:
        buf = self._frame_buf
        n = hop_samples.size
        buf[:-n] = buf[n:]
        buf[-n:] = hop_samples
        mag = np.log1p(100.0 * np.abs(np.fft.rfft(buf * self._window)))
        prev = self._prev_mag
        self._prev_mag = mag
        self._frames_since_update += 1
        if prev is None:
            return
        flux = np.maximum(0.0, mag - prev)
        silent = float(mag.mean()) < self.SILENCE_LEVEL
        for name, mask in self._masks.items():
            self._env[name].append(0.0 if silent else float(flux[mask].mean()))

    # -------------------------------------------------------------- estimation

    @staticmethod
    def _autocorr(envelope: np.ndarray) -> Optional[np.ndarray]:
        e = envelope - envelope.mean()
        n = e.size
        if n < 8 or float(np.dot(e, e)) < 1e-12:
            return None
        spectrum = np.fft.rfft(e, 2 * n)
        r = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
        r = r / (n - np.arange(n))          # unbiased: long lags are not shrunk
        return r / r[0]

    @staticmethod
    def _at(r: Optional[np.ndarray], lags: np.ndarray) -> np.ndarray:
        """Linearly interpolated autocorrelation at fractional lags; 0 past the end."""
        if r is None:
            return np.zeros_like(lags)
        return np.interp(lags, np.arange(r.size), r, right=0.0)

    def _features(self):
        """Autocorrelation of each band, and of their standardised sum."""
        length = len(self._env["mid"])
        if length < self.MIN_HISTORY_S * self.fps:
            return None
        # Onsets are one frame wide and a beat is rarely a whole number of
        # frames, so unsmoothed, the autocorrelation at a fractional lag is
        # split between two bins and reads at half strength while a lag that
        # happens to land on a whole frame reads full: three beats then
        # outscore one. A short blur makes the peaks wider than the rounding.
        bands = {name: np.convolve(np.fromiter(env, dtype=np.float64, count=length),
                                   self._BLUR, mode="same")
                 for name, env in self._env.items()}
        acf = {name: self._autocorr(env) for name, env in bands.items()}
        standardised = [
            (env - env.mean()) / env.std() for env in bands.values() if env.std() > 1e-9
        ]
        if not standardised:
            return None
        acf["all"] = self._autocorr(np.sum(standardised, axis=0))
        if acf["all"] is None:
            return None
        return acf

    def _tatum(self, r_high: Optional[np.ndarray]) -> Optional[float]:
        """The hat grid's period in frames: the shortest strong hat repeat."""
        if r_high is None:
            return None
        lo = max(2, int(self.fps * self.TATUM_RANGE_S[0]))
        hi = min(r_high.size - 2, int(self.fps * self.TATUM_RANGE_S[1]))
        if hi <= lo:
            return None
        seg = r_high[lo:hi + 1]
        peak = float(seg.max())
        if peak < self.TATUM_MIN:
            return None
        for i in range(1, seg.size - 1):
            if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] >= 0.7 * peak:
                a, b, c = seg[i - 1], seg[i], seg[i + 1]
                denom = a - 2.0 * b + c
                shift = 0.5 * (a - c) / denom if denom < 0.0 else 0.0
                return lo + i + max(-0.5, min(0.5, shift))
        return None

    def _score(self, acf) -> Tuple[np.ndarray, np.ndarray]:
        """Score every candidate tempo. Returns (score, pulse)."""
        lag = self._cand_lag
        pulse = np.maximum(0.0, self._at(acf["all"], lag))
        mid = {k: self._at(acf["mid"], lag * k) for k in (2.0 / 3.0, 1.0, 4.0 / 3.0, 2.0, 4.0)}
        # The snare repeats every two beats (or four, in half-time) and on no
        # shorter period. "No shorter" includes two thirds of it: otherwise any
        # steady pulse in the mid band makes a backbeat at 3/2 of its period.
        backbeat = np.maximum(0.0, np.maximum(
            mid[2.0] - np.maximum(mid[1.0], mid[2.0 / 3.0]),
            mid[4.0] - np.maximum(mid[2.0], mid[4.0 / 3.0]),
        ))
        # A real beat makes a bar: the whole kit, and the kick on its own, repeat
        # every four beats. A 3/4 or 2/3 neighbour puts its "bar" at 3 or 6 real
        # beats, where the kick pattern does not line up.
        bar = 0.5 * (np.maximum(0.0, self._at(acf["all"], lag * 4.0))
                     + np.maximum(0.0, self._at(acf["low"], lag * 4.0)))
        # And the hat grid divides it evenly: a beat is two eighths or four
        # sixteenths (or three, swung), never five. That is what rules out 4/5
        # and 2/3 on straight four-on-the-floor, where every bar test passes.
        subdivision = np.ones_like(lag)
        tatum = self._tatum(acf["high"])
        if tatum is not None:
            q = lag / tatum
            n = np.round(q)
            fit = np.exp(-0.5 * ((q - n) / (self.TATUM_TOLERANCE * np.maximum(n, 1.0))) ** 2)
            per_beat = np.array([self.SUBDIVISIONS.get(int(k), 0.0) for k in n])
            subdivision = fit * per_beat
        score = (
            self._prior
            * pulse
            * (1.0 + self.BACKBEAT_GAIN * backbeat)
            * (self.BAR_WEIGHT * bar + (1.0 - self.BAR_WEIGHT))
            * (self.SUBDIVISION_WEIGHT * subdivision + (1.0 - self.SUBDIVISION_WEIGHT))
        )
        return score, pulse

    def estimate(self) -> Tuple[Optional[float], float]:
        """Best tempo for the current window, and a 0..1 confidence in it."""
        acf = self._features()
        if acf is None:
            return None, 0.0
        score, pulse = self._score(acf)

        best = int(np.argmax(score))
        top = float(score[best])
        if top <= 0.0:
            return None, 0.0

        # Parabolic refinement on the log-spaced grid.
        bpm = float(self._cand_bpm[best])
        if 0 < best < score.size - 1:
            a, b, c = score[best - 1], score[best], score[best + 1]
            denom = a - 2.0 * b + c
            if denom < 0.0:
                shift = max(-0.5, min(0.5, 0.5 * (a - c) / denom))
                bpm *= self.GRID_STEP ** shift

        # Confidence: how strong the winning score is in absolute terms (a drum
        # kit scores 0.2-0.3, a sustained pad under 0.03), times how far ahead
        # of the best tempo that is not this one it stands.
        ratio = self._cand_bpm / bpm
        distinct = (ratio > self.SAME_TEMPO_RATIO) | (ratio < 1.0 / self.SAME_TEMPO_RATIO)
        rival = float(score[distinct].max()) if np.any(distinct) else 0.0
        margin = max(0.0, min(1.0, 2.0 * (top - rival) / top))
        strength = max(0.0, min(1.0, top / self.STRONG_SCORE))
        return bpm, strength * (0.25 + 0.75 * margin)

    def _same(self, a: float, b: float) -> bool:
        ratio = a / b
        return 1.0 / self.SAME_TEMPO_RATIO < ratio < self.SAME_TEMPO_RATIO

    def _update(self) -> None:
        bpm, confidence = self.estimate()
        self.raw_bpm, self.raw_confidence = bpm, confidence
        if bpm is None or confidence < self.MIN_CONFIDENCE:
            # Hold the last tempo, but say how little it is worth now.
            self.confidence *= 0.7
            self._candidate, self._candidate_wins = None, 0
            return

        if self.bpm is None or self.confidence < self.MIN_CONFIDENCE:
            self.bpm, self.confidence = bpm, confidence
            self._candidate, self._candidate_wins = None, 0
            return

        if self._same(bpm, self.bpm):
            self.bpm += (bpm - self.bpm) * self.SMOOTHING
            self.confidence += (confidence - self.confidence) * 0.5
            self._candidate, self._candidate_wins = None, 0
            return

        if self._candidate is not None and self._same(bpm, self._candidate):
            self._candidate_wins += 1
        else:
            self._candidate, self._candidate_wins = bpm, 1
        if self._candidate_wins >= self.SWITCH_UPDATES:
            self.bpm, self.confidence = bpm, confidence
            self._candidate, self._candidate_wins = None, 0
        else:
            # Disagreement is evidence against the published tempo.
            self.confidence *= 0.85
