"""Deterministic synthetic audio with ground truth, generated in memory.

Nothing here reads or writes an audio file. Every generator is driven by a
seeded numpy Generator, so two runs of the same call produce bit-identical
samples and identical ground-truth offsets.

Level convention
----------------
Every "reference" render is normalised to REFERENCE_PEAK (0.35 full scale,
about -9 dBFS). That headroom is deliberate: the gain sweep the contract asks
for goes up to +9 dB, and a reference that peaked near full scale would clip
there, which would confound a gain-invariance measurement with clipping
distortion. Loudness differences between tracks live in their RMS, not their
peak.
"""

from dataclasses import dataclass, replace
from typing import Optional, Tuple

import numpy as np
from scipy import signal as _signal

SAMPLE_RATE = 44100
CHUNK_SIZE = 2048

# Reference peak for every "0 dB" render. See module docstring.
REFERENCE_PEAK = 0.35

# Gain sweep the contract names.
GAIN_SWEEP_DB = (-12.0, 0.0, 9.0)

# Quiet bed before the first beat. Deliberately not a whole number of beats at
# any tempo used here: the engine's clock starts at zero, so music that also
# started at zero would hand a free-running phase an accidental lock and hide
# exactly the error this harness exists to measure.
LEAD_IN_S = 0.317

_SEED = 20260804


@dataclass(frozen=True, eq=False)
class SyntheticTrack:
    """A synthesised track plus the ground truth a metric can be scored against."""

    name: str
    samples: np.ndarray
    sample_rate: int
    bpm: float
    beat_samples: Tuple[int, ...]
    downbeat_samples: Tuple[int, ...] = ()
    drop_sample: Optional[int] = None
    tempo_change_sample: Optional[int] = None
    bpm_after: Optional[float] = None
    gain_db: float = 0.0

    @property
    def duration_s(self) -> float:
        return len(self.samples) / float(self.sample_rate)

    @property
    def beat_times(self) -> np.ndarray:
        return np.asarray(self.beat_samples, dtype=np.float64) / float(self.sample_rate)

    @property
    def downbeat_times(self) -> np.ndarray:
        return np.asarray(self.downbeat_samples, dtype=np.float64) / float(self.sample_rate)

    @property
    def drop_time(self) -> Optional[float]:
        if self.drop_sample is None:
            return None
        return self.drop_sample / float(self.sample_rate)

    @property
    def peak(self) -> float:
        return float(np.max(np.abs(self.samples))) if len(self.samples) else 0.0

    @property
    def rms(self) -> float:
        return float(np.sqrt(np.mean(self.samples.astype(np.float64) ** 2))) if len(self.samples) else 0.0

    def with_gain_db(self, db: float) -> "SyntheticTrack":
        """The same performance played back louder or quieter.

        Ground truth is untouched: the beats are in the same places, which is
        the whole point of the gain sweep.
        """
        scale = float(10.0 ** (db / 20.0))
        return replace(
            self,
            name=f"{self.name}@{db:+g}dB",
            samples=(self.samples * scale).astype(np.float32),
            gain_db=self.gain_db + db,
        )


# ---------------------------------------------------------------------------
# Instrument voices
# ---------------------------------------------------------------------------


def _rng(offset: int = 0) -> np.random.Generator:
    return np.random.default_rng(_SEED + offset)


def _bandpass(x: np.ndarray, low: float, high: float, sr: int) -> np.ndarray:
    nyq = sr * 0.5
    low_n = max(1e-4, min(0.99, low / nyq))
    high_n = max(low_n + 1e-4, min(0.99, high / nyq))
    b, a = _signal.butter(2, [low_n, high_n], btype="band")
    return _signal.lfilter(b, a, x).astype(np.float32)


def _highpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    b, a = _signal.butter(2, max(1e-4, min(0.99, cutoff / (sr * 0.5))), btype="high")
    return _signal.lfilter(b, a, x).astype(np.float32)


def _lowpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    b, a = _signal.butter(2, max(1e-4, min(0.99, cutoff / (sr * 0.5))), btype="low")
    return _signal.lfilter(b, a, x).astype(np.float32)


def _kick(sr: int, rng: np.random.Generator, dur: float = 0.26) -> np.ndarray:
    """Pitch-dropping sine body plus a transient click."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    freq = 46.0 + 120.0 * np.exp(-t * 42.0)
    body = np.sin(2.0 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 12.0)
    click = _highpass(rng.standard_normal(n).astype(np.float32), 1800.0, sr) * np.exp(-t * 300.0)
    return (body + 0.35 * click).astype(np.float32)


def _snare(sr: int, rng: np.random.Generator, dur: float = 0.22) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n) / sr
    noise = _bandpass(rng.standard_normal(n).astype(np.float32), 220.0, 7000.0, sr)
    tone = np.sin(2.0 * np.pi * 195.0 * t) * np.exp(-t * 32.0)
    return (noise * np.exp(-t * 22.0) + 0.30 * tone).astype(np.float32)


def _hat(sr: int, rng: np.random.Generator, dur: float = 0.055, open_hat: bool = False) -> np.ndarray:
    n = int(sr * dur * (3.0 if open_hat else 1.0))
    t = np.arange(n) / sr
    noise = _highpass(rng.standard_normal(n).astype(np.float32), 6500.0, sr)
    return (noise * np.exp(-t * (26.0 if open_hat else 95.0))).astype(np.float32)


def _brush(sr: int, rng: np.random.Generator, dur: float = 0.20) -> np.ndarray:
    """Soft brushed-ride texture for the sparse/quiet stand-in."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    noise = _bandpass(rng.standard_normal(n).astype(np.float32), 2500.0, 9000.0, sr)
    return (noise * np.exp(-t * 9.0)).astype(np.float32)


def _bass_note(sr: int, freq: float, dur: float = 0.40) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n) / sr
    attack = np.clip(t / 0.012, 0.0, 1.0)
    body = np.sin(2.0 * np.pi * freq * t) + 0.30 * np.sin(4.0 * np.pi * freq * t)
    return (body * attack * np.exp(-t * 3.4)).astype(np.float32)


def _chord(sr: int, freqs: Tuple[float, ...], dur: float = 1.1) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float32)
    for i, f in enumerate(freqs):
        out += (np.sin(2.0 * np.pi * f * t) / (i + 1.5)).astype(np.float32)
    attack = np.clip(t / 0.02, 0.0, 1.0)
    return (out * attack * np.exp(-t * 1.6)).astype(np.float32)


def _pad(n: int, sr: int, rng: np.random.Generator, freqs: Tuple[float, ...] = (110.0, 165.0, 220.0)) -> np.ndarray:
    """Sustained bed so the analyser's median RMS is not pinned at zero."""
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float32)
    for i, f in enumerate(freqs):
        out += (np.sin(2.0 * np.pi * f * t + i) / (i + 2.0)).astype(np.float32)
    out += 0.4 * _lowpass(rng.standard_normal(n).astype(np.float32), 2500.0, sr)
    return (out / (np.max(np.abs(out)) + 1e-9)).astype(np.float32)


def _place(buffer: np.ndarray, start: int, snippet: np.ndarray, gain: float = 1.0) -> None:
    if start >= len(buffer) or start < 0:
        return
    end = min(len(buffer), start + len(snippet))
    buffer[start:end] += snippet[: end - start] * gain


def _normalise(buffer: np.ndarray, peak: float = REFERENCE_PEAK) -> np.ndarray:
    current = float(np.max(np.abs(buffer))) if len(buffer) else 0.0
    if current <= 0.0:
        return buffer.astype(np.float32)
    return (buffer * (peak / current)).astype(np.float32)


def _master(buffer: np.ndarray, peak: float = REFERENCE_PEAK, drive: float = 3.2) -> np.ndarray:
    """Peak-normalise through a soft-knee saturator.

    Synthesised percussion has a far higher crest factor than any released
    record. Without this the reference render would sit ~15 dB below the
    programme loudness the engine's thresholds were tuned against, and the
    gain sweep would be exercising the wrong end of the range.
    """
    current = float(np.max(np.abs(buffer))) if len(buffer) else 0.0
    if current <= 0.0:
        return buffer.astype(np.float32)
    x = buffer / current
    if drive > 0:
        x = np.tanh(x * drive) / np.tanh(drive)
    return _normalise(x, peak)


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------


def click_track(
    bpm: float = 128.0,
    duration_s: float = 30.0,
    sample_rate: int = SAMPLE_RATE,
    lead_in_s: float = LEAD_IN_S,
    name: str = "click_128",
) -> SyntheticTrack:
    """Exact-BPM kick/click track with backbeat and hats.

    The kick on beat 1 is louder than the others and the snare sits on 2 and 4,
    so the downbeat is inferable from the audio rather than only from a counter.
    """
    rng = _rng(1)
    n = int(sample_rate * duration_s)
    lead = int(round(lead_in_s * sample_rate))
    buf = _pad(n, sample_rate, rng) * 0.10

    kick = _kick(sample_rate, rng)
    snare = _snare(sample_rate, rng)
    hat = _hat(sample_rate, rng)

    beat_period = 60.0 / bpm
    beats = []
    downbeats = []
    index = 0
    while True:
        pos = lead + int(round(index * beat_period * sample_rate))
        if pos >= n:
            break
        in_bar = index % 4
        beats.append(pos)
        if in_bar == 0:
            downbeats.append(pos)
            _place(buf, pos, kick, 1.00)
        elif in_bar == 2:
            _place(buf, pos, kick, 0.72)
        else:
            _place(buf, pos, kick, 0.40)
        if in_bar in (1, 3):
            _place(buf, pos, snare, 0.55)
        _place(buf, pos, hat, 0.16)
        _place(buf, pos + int(0.5 * beat_period * sample_rate), hat, 0.11)
        index += 1

    return SyntheticTrack(
        name=name,
        samples=_master(buf),
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(downbeats),
    )


def tempo_change_track(
    bpm_a: float = 128.0,
    bpm_b: float = 150.0,
    bars_before: int = 8,
    bars_after: int = 8,
    sample_rate: int = SAMPLE_RATE,
    lead_in_s: float = LEAD_IN_S,
    name: str = "tempo_change_128_150",
) -> SyntheticTrack:
    """Same groove, tempo steps on a bar line partway through."""
    rng = _rng(2)
    seconds = lead_in_s + bars_before * 4 * 60.0 / bpm_a + bars_after * 4 * 60.0 / bpm_b + 1.0
    n = int(sample_rate * seconds)
    buf = _pad(n, sample_rate, rng) * 0.10

    kick = _kick(sample_rate, rng)
    snare = _snare(sample_rate, rng)
    hat = _hat(sample_rate, rng)

    beats = []
    downbeats = []
    cursor = float(lead_in_s)
    change_sample = None
    for index in range((bars_before + bars_after) * 4):
        bar = index // 4
        bpm = bpm_a if bar < bars_before else bpm_b
        if bar == bars_before and index % 4 == 0 and change_sample is None:
            change_sample = int(round(cursor * sample_rate))
        pos = int(round(cursor * sample_rate))
        if pos >= n:
            break
        in_bar = index % 4
        beats.append(pos)
        if in_bar == 0:
            downbeats.append(pos)
            _place(buf, pos, kick, 1.00)
        elif in_bar == 2:
            _place(buf, pos, kick, 0.72)
        else:
            _place(buf, pos, kick, 0.40)
        if in_bar in (1, 3):
            _place(buf, pos, snare, 0.55)
        _place(buf, pos, hat, 0.16)
        cursor += 60.0 / bpm

    return SyntheticTrack(
        name=name,
        samples=_master(buf),
        sample_rate=sample_rate,
        bpm=bpm_a,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(downbeats),
        tempo_change_sample=change_sample,
        bpm_after=bpm_b,
    )


def intro_build_drop_track(
    bpm: float = 128.0,
    intro_bars: int = 8,
    build_bars: int = 8,
    drop_bars: int = 12,
    sample_rate: int = SAMPLE_RATE,
    lead_in_s: float = LEAD_IN_S,
    name: str = "intro_build_drop",
) -> SyntheticTrack:
    """Quiet intro, a build, then a hard drop at a known sample offset.

    The drop offset is a bar line, so a detector that lands on musical
    boundaries can be scored against it exactly.
    """
    rng = _rng(3)
    beat_period = 60.0 / bpm
    total_beats = (intro_bars + build_bars + drop_bars) * 4
    lead = int(round(lead_in_s * sample_rate))
    n = lead + int(sample_rate * (total_beats * beat_period + 1.5))
    buf = np.zeros(n, dtype=np.float32)

    pad = _pad(n, sample_rate, rng, freqs=(82.0, 123.0, 165.0))
    kick = _kick(sample_rate, rng)
    snare = _snare(sample_rate, rng)
    hat = _hat(sample_rate, rng)
    open_hat = _hat(sample_rate, rng, open_hat=True)

    intro_beats = intro_bars * 4
    build_beats = build_bars * 4
    drop_sample = lead + int(round((intro_beats + build_beats) * beat_period * sample_rate))

    # Intro: pad only, at a low level, with a soft kick every bar.
    intro_end = lead + int(round(intro_beats * beat_period * sample_rate))
    buf[:intro_end] += pad[:intro_end] * 0.10

    # Build: pad swells, a riser climbs, snare rolls subdivide.
    build_end = drop_sample
    build_len = build_end - intro_end
    ramp = np.linspace(0.0, 1.0, max(1, build_len), dtype=np.float32)
    buf[intro_end:build_end] += pad[intro_end:build_end] * (0.12 + 0.55 * ramp)
    riser = rng.standard_normal(build_len).astype(np.float32)
    riser = _highpass(riser, 900.0, sample_rate) * (ramp ** 2)
    buf[intro_end:build_end] += riser * 0.35

    beats = []
    downbeats = []
    for index in range(total_beats):
        pos = lead + int(round(index * beat_period * sample_rate))
        if pos >= n:
            break
        beats.append(pos)
        in_bar = index % 4
        if in_bar == 0:
            downbeats.append(pos)

        if index < intro_beats:
            if in_bar == 0:
                _place(buf, pos, kick, 0.28)
            _place(buf, pos, hat, 0.05)
            continue

        if index < intro_beats + build_beats:
            progress = (index - intro_beats) / max(1, build_beats)
            _place(buf, pos, kick, 0.35 + 0.35 * progress)
            # Snare roll subdivides as the build progresses.
            divisions = 2 if progress < 0.5 else (4 if progress < 0.85 else 8)
            for d in range(divisions):
                sub = pos + int(round(d * beat_period * sample_rate / divisions))
                _place(buf, sub, snare, 0.18 + 0.35 * progress)
            _place(buf, pos, hat, 0.10)
            continue

        # Drop: everything at full weight, four on the floor plus open hats.
        _place(buf, pos, kick, 1.00 if in_bar == 0 else 0.92)
        if in_bar in (1, 3):
            _place(buf, pos, snare, 0.72)
        _place(buf, pos, hat, 0.22)
        _place(buf, pos + int(0.5 * beat_period * sample_rate), open_hat, 0.20)
        _place(buf, pos, _bass_note(sample_rate, 55.0, beat_period * 0.95), 0.55)

    buf[drop_sample:] += pad[drop_sample:] * 0.45

    return SyntheticTrack(
        name=name,
        samples=_master(buf, drive=2.4),
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(downbeats),
        drop_sample=drop_sample,
    )


def sparse_quiet_track(
    bpm: float = 96.0,
    duration_s: float = 24.0,
    sample_rate: int = SAMPLE_RATE,
    lead_in_s: float = LEAD_IN_S,
    name: str = "sparse_quiet_trio",
) -> SyntheticTrack:
    """Jazz-trio stand-in: brushes, walking bass, occasional chord, low level.

    Peaks well below the reference and is left unmastered, so the loudness
    difference against the dense track is real programme dynamics rather than a
    normalisation artefact.
    """
    rng = _rng(4)
    n = int(sample_rate * duration_s)
    lead = int(round(lead_in_s * sample_rate))
    buf = np.zeros(n, dtype=np.float32)

    beat_period = 60.0 / bpm
    walk = [55.0, 61.7, 65.4, 73.4, 82.4, 73.4, 65.4, 58.3]
    beats = []
    downbeats = []
    index = 0
    while True:
        pos = lead + int(round(index * beat_period * sample_rate))
        if pos >= n:
            break
        beats.append(pos)
        if index % 4 == 0:
            downbeats.append(pos)
        _place(buf, pos, _bass_note(sample_rate, walk[index % len(walk)], beat_period * 0.9), 0.60)
        _place(buf, pos, _brush(sample_rate, rng), 0.20)
        # Swung upbeat brush at two thirds of the beat.
        _place(buf, pos + int(round(beat_period * sample_rate * 0.66)), _brush(sample_rate, rng), 0.12)
        if index % 8 == 0:
            _place(buf, pos, _chord(sample_rate, (196.0, 246.9, 293.7, 370.0)), 0.28)
        index += 1

    buf = _normalise(buf, peak=REFERENCE_PEAK * 0.34)
    return SyntheticTrack(
        name=name,
        samples=buf,
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(downbeats),
    )


def dense_loud_track(
    bpm: float = 140.0,
    duration_s: float = 24.0,
    sample_rate: int = SAMPLE_RATE,
    lead_in_s: float = LEAD_IN_S,
    name: str = "dense_loud",
) -> SyntheticTrack:
    """Dense, loud, four-on-the-floor material at the same peak ceiling.

    Same peak as the reference renders, much higher RMS: the pair is there to
    show what a level-driven threshold ladder does across real programme
    loudness, not across peak level.
    """
    rng = _rng(5)
    n = int(sample_rate * duration_s)
    lead = int(round(lead_in_s * sample_rate))
    buf = _pad(n, sample_rate, rng, freqs=(65.4, 98.0, 130.8, 196.0)) * 0.55

    kick = _kick(sample_rate, rng)
    snare = _snare(sample_rate, rng)
    hat = _hat(sample_rate, rng)

    beat_period = 60.0 / bpm
    beats = []
    downbeats = []
    index = 0
    while True:
        pos = lead + int(round(index * beat_period * sample_rate))
        if pos >= n:
            break
        beats.append(pos)
        if index % 4 == 0:
            downbeats.append(pos)
        _place(buf, pos, kick, 1.00 if index % 4 == 0 else 0.90)
        if index % 4 in (1, 3):
            _place(buf, pos, snare, 0.70)
        _place(buf, pos, hat, 0.22)
        _place(buf, pos + int(0.5 * beat_period * sample_rate), hat, 0.18)
        _place(buf, pos, _bass_note(sample_rate, 65.4, beat_period * 0.9), 0.65)
        index += 1

    return SyntheticTrack(
        name=name,
        samples=_master(buf),
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(downbeats),
    )


# Genre-shaped drum grids for tempo tests. Positions are in beats within a
# four-beat bar; ``hats`` is hats per beat. These are the patterns that used to
# fool the tempo estimate: drum & bass and half-time read at 3/4 or 4/3, and
# hip-hop read at double time, because the kick alone does not mark the beat.
DRUM_PATTERNS = {
    "four_floor": dict(bpm=128.0, kicks=(0, 1, 2, 3), snares=(1, 3), hats=2),
    "house": dict(bpm=124.0, kicks=(0, 1, 2, 3), snares=(1, 3), hats=4),
    "techno": dict(bpm=132.0, kicks=(0, 1, 2, 3), snares=(), hats=4),
    "dnb": dict(bpm=174.0, kicks=(0, 2.5), snares=(1, 3), hats=2),
    "dnb_sparse": dict(bpm=172.0, kicks=(0, 2.75), snares=(1, 3), hats=4),
    "halftime": dict(bpm=140.0, kicks=(0,), snares=(2,), hats=4),
    "trap_halftime": dict(bpm=150.0, kicks=(0, 1.75), snares=(2,), hats=4),
    "hiphop": dict(bpm=92.0, kicks=(0, 1.5, 2.5), snares=(1, 3), hats=2),
}


def drum_pattern_track(
    style: str,
    bars: int = 24,
    sample_rate: int = SAMPLE_RATE,
    lead_in_s: float = LEAD_IN_S,
    seed_offset: int = 7,
) -> SyntheticTrack:
    """One of the DRUM_PATTERNS over a quiet pad, with beat and bar truth.

    ``bpm`` is the tempo an operator would count, which for half-time styles
    is the hat and kick grid, not the snare.
    """
    spec = DRUM_PATTERNS[style]
    bpm = float(spec["bpm"])
    rng = _rng(seed_offset)
    period = 60.0 / bpm
    lead = int(round(lead_in_s * sample_rate))
    n = lead + int(bars * 4 * period * sample_rate) + sample_rate
    buf = _pad(n, sample_rate, rng) * 0.10
    kick = _kick(sample_rate, rng)
    snare = _snare(sample_rate, rng)
    hat = _hat(sample_rate, rng)

    beats = []
    downbeats = []
    for bar in range(bars):
        bar_start = lead + bar * 4 * period * sample_rate
        downbeats.append(int(round(bar_start)))
        for i in range(4):
            beats.append(int(round(bar_start + i * period * sample_rate)))
        for p in spec["kicks"]:
            _place(buf, int(round(bar_start + p * period * sample_rate)), kick, 1.0)
        for p in spec["snares"]:
            _place(buf, int(round(bar_start + p * period * sample_rate)), snare, 0.7)
        per_beat = spec["hats"]
        for j in range(4 * per_beat):
            _place(buf, int(round(bar_start + j / per_beat * period * sample_rate)), hat, 0.15)

    return SyntheticTrack(
        name=f"drums_{style}",
        samples=_master(buf),
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(downbeats),
    )


# Chord progressions, one chord per bar, as frequency triads. "a_minor" and
# "a_minor_chorus" share a key (the chorus adds an E major's G sharp, as real
# choruses do); "e_flat" is three flats away, the kind of key change a DJ makes
# going into the next record.
PROGRESSIONS = {
    "a_minor": ((220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (261.6, 329.6, 392.0), (196.0, 246.9, 293.7)),
    "a_minor_chorus": ((293.7, 349.2, 440.0), (220.0, 261.6, 329.6), (329.6, 415.3, 493.9), (220.0, 261.6, 329.6)),
    "e_flat": ((311.1, 392.0, 466.2), (207.7, 261.6, 311.1), (233.1, 293.7, 349.2), (261.6, 311.1, 392.0)),
}


def _song_buffer(
    progression: Tuple[Tuple[float, ...], ...],
    bars: int,
    bpm: float,
    sample_rate: int,
    rng: np.random.Generator,
    hats_per_beat: int = 2,
    breakdown: Tuple[int, int] = (-1, -1),
    chorus: Optional[Tuple[Tuple[float, ...], ...]] = None,
    chorus_bars: Tuple[int, int] = (-1, -1),
) -> np.ndarray:
    """Chord stabs, root bass and a four-on-the-floor kit, starting at sample 0.

    Bars in `breakdown` keep the chords and lose the drums and bass. Bars in
    `chorus_bars` play `chorus` instead of `progression`.
    """
    period = 60.0 / bpm
    n = int(round(bars * 4 * period * sample_rate))
    buf = np.zeros(n, dtype=np.float32)
    kick, snare, hat = _kick(sample_rate, rng), _snare(sample_rate, rng), _hat(sample_rate, rng)
    for bar in range(bars):
        chords = chorus if (chorus and chorus_bars[0] <= bar < chorus_bars[1]) else progression
        triad = chords[bar % len(chords)]
        stab = _chord(sample_rate, triad, dur=period * 0.9)
        drums = not (breakdown[0] <= bar < breakdown[1])
        for beat in range(4):
            pos = int(round((bar * 4 + beat) * period * sample_rate))
            _place(buf, pos, stab, 0.45)
            if not drums:
                continue
            _place(buf, pos, kick, 1.0)
            if beat in (1, 3):
                _place(buf, pos, snare, 0.6)
            for j in range(hats_per_beat):
                _place(buf, pos + int(round(j / hats_per_beat * period * sample_rate)), hat, 0.15)
            _place(buf, pos, _bass_note(sample_rate, triad[0] / 4.0, period * 0.9), 0.5)
    return buf


def song_track(
    progression: str = "a_minor",
    bars: int = 64,
    bpm: float = 126.0,
    breakdown: Tuple[int, int] = (-1, -1),
    chorus_bars: Tuple[int, int] = (-1, -1),
    sample_rate: int = SAMPLE_RATE,
    name: Optional[str] = None,
) -> SyntheticTrack:
    """One track with harmony, optionally with a breakdown and a same-key chorus.

    The negative case for track-change detection: everything here is one record.
    """
    rng = _rng(11)
    lead = int(round(LEAD_IN_S * sample_rate))
    body = _song_buffer(
        PROGRESSIONS[progression], bars, bpm, sample_rate, rng,
        breakdown=breakdown, chorus=PROGRESSIONS["a_minor_chorus"], chorus_bars=chorus_bars,
    )
    buf = np.zeros(lead + len(body) + sample_rate, dtype=np.float32)
    buf[lead:lead + len(body)] += body
    period = 60.0 / bpm
    beats = tuple(lead + int(round(i * period * sample_rate)) for i in range(bars * 4))
    return SyntheticTrack(
        name=name or f"song_{progression}",
        samples=_master(buf),
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=beats,
        downbeat_samples=beats[::4],
    )


def dj_mix_track(
    bpm: float = 126.0,
    outgoing_bars: int = 40,
    blend_bars: int = 16,
    incoming_bars: int = 40,
    incoming: str = "e_flat",
    incoming_bpm: Optional[float] = None,
    sample_rate: int = SAMPLE_RATE,
    name: Optional[str] = None,
) -> SyntheticTrack:
    """Two records beatmatched and crossfaded with no gap, as a DJ mixes them.

    The incoming record starts at bar `outgoing_bars`, plays under the outgoing
    one for `blend_bars` on an equal-power crossfade, then carries on alone.
    Ground truth: `tempo_change_sample` marks the middle of the blend, the
    earliest instant a listener would say the new track has taken over.
    """
    rng_a, rng_b = _rng(21), _rng(22)
    lead = int(round(LEAD_IN_S * sample_rate))
    period = 60.0 / bpm
    bar_samples = 4 * period * sample_rate
    out_bars = outgoing_bars + blend_bars
    a = _song_buffer(PROGRESSIONS["a_minor"], out_bars, bpm, sample_rate, rng_a)
    in_bpm = incoming_bpm or bpm
    b = _song_buffer(PROGRESSIONS[incoming], blend_bars + incoming_bars, in_bpm, sample_rate, rng_b, hats_per_beat=4)

    start_b = int(round(outgoing_bars * bar_samples))
    blend_len = int(round(blend_bars * bar_samples))
    n = lead + max(len(a), start_b + len(b)) + sample_rate
    buf = np.zeros(n, dtype=np.float32)

    fade = np.linspace(0.0, 1.0, blend_len, dtype=np.float32)
    a_gain = np.ones(len(a), dtype=np.float32)
    a_gain[start_b:start_b + blend_len] = np.cos(fade * np.pi / 2.0)
    a_gain[start_b + blend_len:] = 0.0
    b_gain = np.ones(len(b), dtype=np.float32)
    b_gain[:blend_len] = np.sin(fade * np.pi / 2.0)
    buf[lead:lead + len(a)] += a * a_gain
    buf[lead + start_b:lead + start_b + len(b)] += b * b_gain

    beats = [lead + int(round(i * period * sample_rate)) for i in range((outgoing_bars + blend_bars) * 4)]
    in_period = 60.0 / in_bpm
    beats += [
        lead + start_b + int(round(i * in_period * sample_rate))
        for i in range(blend_bars * 4, (blend_bars + incoming_bars) * 4)
    ]
    return SyntheticTrack(
        name=name or f"dj_mix_a_minor_to_{incoming}",
        samples=_master(buf),
        sample_rate=sample_rate,
        bpm=bpm,
        beat_samples=tuple(beats),
        downbeat_samples=tuple(beats[::4]),
        tempo_change_sample=lead + start_b + blend_len // 2,
        bpm_after=in_bpm,
    )


def silence_track(duration_s: float = 4.0, sample_rate: int = SAMPLE_RATE) -> SyntheticTrack:
    """No input at all. The rig must go dark and stay dark."""
    return SyntheticTrack(
        name="silence",
        samples=np.zeros(int(sample_rate * duration_s), dtype=np.float32),
        sample_rate=sample_rate,
        bpm=0.0,
        beat_samples=(),
    )


def with_silence_tail(track: SyntheticTrack, seconds: float = 3.0) -> SyntheticTrack:
    """The track followed by digital silence.

    Any running normalisation will have wound its gain up by the end of the
    music, so this is where "silence must stay silent" is actually decided.
    """
    tail = np.zeros(int(round(seconds * track.sample_rate)), dtype=np.float32)
    return replace(
        track,
        name=f"{track.name}+silence",
        samples=np.concatenate([track.samples, tail]).astype(np.float32),
    )


def gain_sweep(track: SyntheticTrack, gains_db=GAIN_SWEEP_DB):
    """The same track at each gain in the sweep."""
    return [track if db == 0.0 else track.with_gain_db(db) for db in gains_db]


def iter_chunks(track: SyntheticTrack, chunk_size: int = CHUNK_SIZE):
    """Whole chunks of the track, as the capture device would deliver them.

    A trailing partial chunk is dropped: the live capture path only ever hands
    the analyser full buffers, and a short final FFT would change the frame's
    spectrum for reasons that have nothing to do with the music.
    """
    total = (len(track.samples) // chunk_size) * chunk_size
    for start in range(0, total, chunk_size):
        yield start, track.samples[start:start + chunk_size]
