"""Drive the real analyser and the real engine, and measure what comes out.

This module deliberately contains no model of how the show *should* behave. It
runs `AudioAnalyzer.process_chunk` and `EffectsEngine.update`, captures DMX
through the engine's own callback, and reduces those frames to numbers. A
harness that reimplemented the engine would prove nothing about the engine.

Timeline
--------
Audio and lighting share one virtual timeline measured in seconds from the
start of the track.

* A chunk covering samples [i, i+N) is stamped at (i+N)/sample_rate. That is
  the earliest instant a real capture path could have those samples, so beat
  timings measured here include the same inherent quantisation a live show
  gets (one chunk = 46.4 ms at 44100/2048).
* Engine frames run at `fps` and are advanced only as far as the audio
  timeline has reached, which reproduces the live arrangement of a 60 fps
  render loop fed by a ~21.5 Hz analysis loop.

Both the analyser and the engine read wall clocks (`datetime.utcnow()`,
`time.time()`) to time beats, section holds and effect timers. Offline the
samples arrive hundreds of times faster than real time, so those clocks are
redirected to the virtual timeline for the duration of a run. Nothing else
about either object is replaced.
"""

from __future__ import annotations

import contextlib
import importlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.services.audio.audio_analyzer import AudioAnalyzer
from app.services.effects.effects_engine import EffectsEngine, EffectsConfig

from .synthetic_audio import CHUNK_SIZE, SyntheticTrack, iter_chunks

# Modules whose wall clock has to follow the virtual timeline. Each does a
# plain `import time` and calls `time.time()` inside the update path.
_TIME_PATCH_MODULES = (
    "app.services.effects.effects_engine",
    "app.services.effects.decision_engine",
    "app.services.effects.lfo_engine",
    "app.services.lighting.section_manager",
    "app.services.lighting.beam_look_scheduler",
)

_ANALYZER_MODULE = "app.services.audio.audio_analyzer"
_CLOCK_EPOCH = datetime(2024, 1, 1)

# The un-accented reference configuration. Every contract metric baseline in
# test_musical_behaviour.py was recorded against this, so it is held fixed for
# comparability. It is NOT what the venue runs: accents are off and no governor
# is attached, so nothing measured through it says anything about flash rate.
LIVE_ENGINE_KWARGS = {
    "fps": 60.0,
    "auto_mode": True,
    "movement_enabled": True,
    "dimmer_enabled": True,
    "strobe_enabled": False,
}

# What app/main.py:225-239 actually builds. Anything asserting a safety property
# — flash rate, duty cycle, the no_strobe off switch — has to run against this
# and through `build_venue_engine`, because the accent governor is part of the
# machine that enforces those properties.
VENUE_ENGINE_KWARGS = {
    "fps": 60.0,
    "auto_mode": True,
    "movement_enabled": True,
    "dimmer_enabled": True,
    "strobe_enabled": True,
    "accessibility_mode": "conservative",
    "strobe_hz_cap": 3.0,
    "strobe_max_duty_cycle": 0.34,
    "strobe_burst_max_s": 0.10,
    "strobe_refractory_s": 0.30,
}


class _Clock:
    """The single virtual timeline both the analyser and the engine read."""

    __slots__ = ("t",)

    def __init__(self) -> None:
        self.t = 0.0


class _TimeShim:
    def __init__(self, clock: _Clock, real):
        self._clock = clock
        self._real = real

    def time(self) -> float:
        return self._clock.t

    def monotonic(self) -> float:
        return self._clock.t

    def perf_counter(self) -> float:
        return self._clock.t

    def __getattr__(self, name):
        return getattr(self._real, name)


class _DatetimeShim:
    """Only `utcnow` is redirected; everything else is the real class."""

    def __init__(self, clock: _Clock, real):
        self._clock = clock
        self._real = real

    def utcnow(self):
        return _CLOCK_EPOCH + timedelta(seconds=self._clock.t)

    def __getattr__(self, name):
        return getattr(self._real, name)


@contextlib.contextmanager
def virtual_clock(clock: _Clock):
    """Point every clock in the analysis and render path at `clock`."""
    patched = []
    try:
        analyzer_mod = importlib.import_module(_ANALYZER_MODULE)
        patched.append((analyzer_mod, "datetime", analyzer_mod.datetime))
        analyzer_mod.datetime = _DatetimeShim(clock, analyzer_mod.datetime)
        patched.append((analyzer_mod, "time", analyzer_mod.time))
        analyzer_mod.time = _TimeShim(clock, analyzer_mod.time)

        for name in _TIME_PATCH_MODULES:
            mod = importlib.import_module(name)
            real = getattr(mod, "time", None)
            if real is None:
                continue
            patched.append((mod, "time", real))
            mod.time = _TimeShim(clock, real)
        yield
    finally:
        for mod, attr, real in reversed(patched):
            setattr(mod, attr, real)


# ---------------------------------------------------------------------------
# Reading the wire
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FixtureTap:
    """Where one fixture's intensity and colour live in the DMX frame."""

    fixture_id: str
    universe: int
    dimmer: Optional[int]
    red: Optional[int]
    green: Optional[int]
    blue: Optional[int]


def _build_taps(engine: EffectsEngine) -> Tuple[_FixtureTap, ...]:
    taps = []
    for fixture in engine.fixtures.fixtures.values():
        base = int(getattr(fixture, "dmx_address", 0) or 0) - 1
        if base < 0:
            continue
        channels = getattr(fixture, "channels", {}) or {}

        def addr(name: str) -> Optional[int]:
            if name not in channels:
                return None
            a = base + int(channels[name])
            return a if 0 <= a < 512 else None

        taps.append(_FixtureTap(
            fixture_id=str(fixture.id),
            universe=int(getattr(fixture, "universe", 0) or 0),
            dimmer=addr("dimmer"),
            red=addr("red"),
            green=addr("green"),
            blue=addr("blue"),
        ))
    return tuple(sorted(taps, key=lambda t: (t.universe, t.dimmer if t.dimmer is not None else 10 ** 6, t.fixture_id)))


def _read_frame(taps: Sequence[_FixtureTap], frames: Dict[int, List[int]]) -> Tuple[np.ndarray, bool]:
    """Per-fixture emitted intensity (0..1) and whether anything is flashing white."""
    intensity = np.zeros(len(taps), dtype=np.float64)
    white = False
    for i, tap in enumerate(taps):
        frame = frames.get(tap.universe)
        if frame is None:
            continue
        rgb = [
            frame[tap.red] if tap.red is not None else None,
            frame[tap.green] if tap.green is not None else None,
            frame[tap.blue] if tap.blue is not None else None,
        ]
        if tap.dimmer is not None:
            level = frame[tap.dimmer] / 255.0
        else:
            # No intensity channel: intensity rides in the colour values.
            present = [v for v in rgb if v is not None]
            level = (max(present) / 255.0) if present else 0.0
        intensity[i] = level
        if level >= 0.88 and all(v is not None and v >= 248 for v in rgb):
            white = True
    return intensity, white


# ---------------------------------------------------------------------------
# Engine phase readout
# ---------------------------------------------------------------------------


def _engine_beat_phase(engine: EffectsEngine) -> float:
    """The phase the renderer is actually running its beat-locked motion on.

    Preference order matters: if a later change gives the engine a real
    phase-locked clock it will be published as an attribute and read from
    there. The fallback mirrors the one-line expression in
    `_update_fixtures_rebuild`, which today derives phase from the engine's
    free-running wall clock and has no accessor at all.
    """
    for name in ("beat_phase", "current_beat_phase", "musical_beat_phase"):
        value = getattr(engine, name, None)
        if isinstance(value, (int, float)):
            return float(value) % 1.0
    bpm = max(60.0, min(190.0, float(getattr(engine, "_smoothed_movement_bpm", 128.0))))
    return (float(engine.time) * (bpm / 60.0)) % 1.0


def _engine_bar_phase(engine: EffectsEngine) -> float:
    """Position within the 4-beat bar the renderer is stepping patterns on."""
    for name in ("bar_phase", "current_bar_phase", "musical_bar_phase"):
        value = getattr(engine, name, None)
        if isinstance(value, (int, float)):
            return float(value) % 1.0
    bpm = max(60.0, min(190.0, float(getattr(engine, "_smoothed_movement_bpm", 128.0))))
    return ((float(engine.time) * (bpm / 60.0)) / 4.0) % 1.0


def _engine_bpm(engine: EffectsEngine) -> float:
    return max(60.0, min(190.0, float(getattr(engine, "_smoothed_movement_bpm", 128.0))))


def _engine_section(engine: EffectsEngine) -> str:
    """The section the live renderer is drawing right now.

    `_rebuild_section` is what `_update_fixtures_rebuild` switches on; the
    section manager is read as a fallback so the metric survives a detector
    swap.
    """
    value = getattr(engine, "_rebuild_section", None)
    if isinstance(value, str) and value:
        return value.lower()
    manager = getattr(engine, "section_manager", None)
    current = getattr(manager, "current_section", None)
    return str(getattr(current, "value", current) or "unknown").lower()


# ---------------------------------------------------------------------------
# Analyser -> engine wiring (mirrors app/main.py on_audio_chunk)
# ---------------------------------------------------------------------------

# Fields a normalised-loudness stage would publish alongside the raw RMS.
# Absent today; read opportunistically so the harness reports it once it lands.
_NORMALISED_ENERGY_KEYS = (
    "normalized_energy",
    "normalised_energy",
    "energy_normalized",
    "rms_energy_normalized",
    "loudness_normalized",
)


def analysis_to_engine_kwargs(analysis: dict) -> dict:
    """Exactly the mapping app/main.py applies between analyser and engine."""
    beat = analysis.get("beat", {}) or {}
    mood = analysis.get("mood", {}) or {}
    freq = analysis.get("frequency", {}) or {}
    ml_data = analysis.get("ml", {}) or {}

    bands = {b.get("name"): b.get("energy", 0.0) for b in freq.get("bands", [])}
    bass_energy = bands.get("bass", 0.0) + bands.get("sub_bass", 0.0)
    mid_energy = bands.get("mid", 0.0) + bands.get("low_mid", 0.0)
    high_energy = bands.get("high", 0.0) + bands.get("high_mid", 0.0)

    return {
        "energy": min(1.0, float(freq.get("rms_energy", 0.0)) * 2.0),
        "bass": min(1.0, float(bass_energy)),
        "mid": min(1.0, float(mid_energy)),
        "high": min(1.0, float(high_energy)),
        "is_beat": bool(beat.get("is_beat", False)),
        "beat_number": int(beat.get("beat_count", beat.get("beat_position", 1))),
        "valence": float(mood.get("valence", 0.0)),
        "arousal": float(mood.get("arousal", 0.0)),
        "spectral_flux": min(1.0, float(freq.get("spectral_flux", 0.0)) * 10.0),
        "bpm": float(beat.get("bpm", 128.0)),
        "ml_data": ml_data,
    }


def build_engine(**overrides) -> EffectsEngine:
    """The un-accented reference engine the contract baselines were taken on."""
    kwargs = dict(LIVE_ENGINE_KWARGS)
    kwargs.update(overrides)
    engine = EffectsEngine(EffectsConfig(**kwargs))
    engine.enable_pro_lighting(True)
    from app.services.lighting.genre_profiles import Genre
    engine.set_genre(Genre.EDM)
    return engine


def build_venue_engine(**overrides) -> EffectsEngine:
    """The engine the venue runs: main.py's posture, with the accent governor.

    `attach_accent_governor` wraps `engine.update`, so it has to be attached
    here rather than by the caller — the governor writes `strobe_enabled` and
    `audience_intensity_cap` on the frame immediately before the one that reads
    them, and a run that skips it is measuring a different machine.
    """
    kwargs = dict(VENUE_ENGINE_KWARGS)
    kwargs.update(overrides)
    engine = EffectsEngine(EffectsConfig(**kwargs))
    engine.enable_pro_lighting(True)
    from app.services.lighting.genre_profiles import Genre
    engine.set_genre(Genre.EDM)
    from app.services.lighting.pro_effects import attach_accent_governor
    attach_accent_governor(engine)
    return engine


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Everything one pass over a track produced, as arrays over time."""

    track_name: str
    gain_db: float
    fps: float
    duration_s: float
    fixture_ids: Tuple[str, ...]

    frame_times: np.ndarray
    intensity: np.ndarray          # (frames, fixtures), 0..1 read off the wire
    white_flash: np.ndarray        # (frames,) bool
    sections: List[str]
    beat_phase: np.ndarray
    bar_phase: np.ndarray
    engine_bpm: np.ndarray

    chunk_times: np.ndarray
    chunk_energy: np.ndarray       # value handed to EffectsEngine.update_audio
    chunk_rms: np.ndarray          # raw analyser rms_energy
    chunk_bass: np.ndarray
    chunk_bpm: np.ndarray
    detected_beat_times: np.ndarray
    normalised_energy: Optional[np.ndarray] = None

    @property
    def rig_mean(self) -> np.ndarray:
        if self.intensity.size == 0:
            return np.zeros(0)
        return self.intensity.mean(axis=1)

    @property
    def frame_count(self) -> int:
        return int(self.intensity.shape[0])

    def between(self, start_s: float, end_s: float) -> "RunResult":
        """The same run restricted to a window, so metrics can be scoped."""
        mask = (self.frame_times >= start_s) & (self.frame_times < end_s)
        chunk_mask = (self.chunk_times >= start_s) & (self.chunk_times < end_s)
        beats = self.detected_beat_times
        return RunResult(
            track_name=self.track_name,
            gain_db=self.gain_db,
            fps=self.fps,
            duration_s=max(0.0, min(end_s, self.duration_s) - start_s),
            fixture_ids=self.fixture_ids,
            frame_times=self.frame_times[mask],
            intensity=self.intensity[mask],
            white_flash=self.white_flash[mask],
            sections=[s for s, keep in zip(self.sections, mask) if keep],
            beat_phase=self.beat_phase[mask],
            bar_phase=self.bar_phase[mask],
            engine_bpm=self.engine_bpm[mask],
            chunk_times=self.chunk_times[chunk_mask],
            chunk_energy=self.chunk_energy[chunk_mask],
            chunk_rms=self.chunk_rms[chunk_mask],
            chunk_bass=self.chunk_bass[chunk_mask],
            chunk_bpm=self.chunk_bpm[chunk_mask],
            detected_beat_times=beats[(beats >= start_s) & (beats < end_s)],
            normalised_energy=(
                None if self.normalised_energy is None else self.normalised_energy[chunk_mask]
            ),
        )


async def run_track(
    track: SyntheticTrack,
    *,
    fps: float = 60.0,
    chunk_size: int = CHUNK_SIZE,
    engine: Optional[EffectsEngine] = None,
    analyzer: Optional[AudioAnalyzer] = None,
    **engine_overrides,
) -> RunResult:
    """Play `track` through the real analyser and the real engine.

    Exceptions from `EffectsEngine.update` are deliberately not caught: a raise
    inside the 60 fps path is the failure this codebase most needs to see.
    """
    engine = engine if engine is not None else build_engine(**engine_overrides)
    analyzer = analyzer if analyzer is not None else AudioAnalyzer()
    analyzer.sample_rate = track.sample_rate

    taps = _build_taps(engine)
    captured: Dict[int, List[int]] = {}

    def dmx_callback(universe: int, frame: List[int]) -> None:
        captured[int(universe)] = list(frame)

    engine.set_dmx_callback(dmx_callback)

    clock = _Clock()
    dt = 1.0 / float(fps)

    frame_times: List[float] = []
    intensities: List[np.ndarray] = []
    whites: List[bool] = []
    sections: List[str] = []
    beat_phases: List[float] = []
    bar_phases: List[float] = []
    engine_bpms: List[float] = []

    chunk_times: List[float] = []
    chunk_energy: List[float] = []
    chunk_rms: List[float] = []
    chunk_bass: List[float] = []
    chunk_bpm: List[float] = []
    detected_beats: List[float] = []
    normalised: List[float] = []
    saw_normalised = False

    engine_time = 0.0

    with virtual_clock(clock):
        for start, chunk in iter_chunks(track, chunk_size):
            chunk_end = (start + len(chunk)) / float(track.sample_rate)
            clock.t = chunk_end

            analysis = await analyzer.process_chunk(np.asarray(chunk, dtype=np.float32))
            kwargs = analysis_to_engine_kwargs(analysis)
            engine.update_audio(**kwargs)

            freq = analysis.get("frequency", {}) or {}
            chunk_times.append(chunk_end)
            chunk_energy.append(kwargs["energy"])
            chunk_rms.append(float(freq.get("rms_energy", 0.0)))
            chunk_bass.append(kwargs["bass"])
            chunk_bpm.append(kwargs["bpm"])
            if kwargs["is_beat"]:
                detected_beats.append(chunk_end)
            for key in _NORMALISED_ENERGY_KEYS:
                if key in freq:
                    saw_normalised = True
                    normalised.append(float(freq[key]))
                    break
            else:
                normalised.append(float("nan"))

            while engine_time + dt <= chunk_end + 1e-9:
                engine_time += dt
                clock.t = engine_time
                captured.clear()
                engine.update(delta_time=dt)

                level, white = _read_frame(taps, captured)
                frame_times.append(float(engine.time))
                intensities.append(level)
                whites.append(white)
                sections.append(_engine_section(engine))
                beat_phases.append(_engine_beat_phase(engine))
                bar_phases.append(_engine_bar_phase(engine))
                engine_bpms.append(_engine_bpm(engine))

    return RunResult(
        track_name=track.name,
        gain_db=track.gain_db,
        fps=float(fps),
        duration_s=track.duration_s,
        fixture_ids=tuple(t.fixture_id for t in taps),
        frame_times=np.asarray(frame_times, dtype=np.float64),
        intensity=(np.vstack(intensities) if intensities else np.zeros((0, len(taps)))),
        white_flash=np.asarray(whites, dtype=bool),
        sections=sections,
        beat_phase=np.asarray(beat_phases, dtype=np.float64),
        bar_phase=np.asarray(bar_phases, dtype=np.float64),
        engine_bpm=np.asarray(engine_bpms, dtype=np.float64),
        chunk_times=np.asarray(chunk_times, dtype=np.float64),
        chunk_energy=np.asarray(chunk_energy, dtype=np.float64),
        chunk_rms=np.asarray(chunk_rms, dtype=np.float64),
        chunk_bass=np.asarray(chunk_bass, dtype=np.float64),
        chunk_bpm=np.asarray(chunk_bpm, dtype=np.float64),
        detected_beat_times=np.asarray(detected_beats, dtype=np.float64),
        normalised_energy=(np.asarray(normalised, dtype=np.float64) if saw_normalised else None),
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhaseError:
    """How far the engine's musical phase sits from the true grid."""

    count: int
    mean_ms: float
    worst_ms: float
    mean_fraction: float
    worst_fraction: float

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "mean_ms": round(self.mean_ms, 1),
            "worst_ms": round(self.worst_ms, 1),
            "mean_fraction": round(self.mean_fraction, 4),
            "worst_fraction": round(self.worst_fraction, 4),
        }


_EMPTY_PHASE = PhaseError(0, float("nan"), float("nan"), float("nan"), float("nan"))


def _phase_error(
    result: RunResult,
    true_times: np.ndarray,
    phases: np.ndarray,
    cycles_per_beat: float,
    warmup_s: float,
) -> PhaseError:
    """Distance from each true event to the nearest zero crossing of `phases`.

    The engine frame nearest the true event is used, then the phase is carried
    the remaining few milliseconds to the event itself so frame quantisation
    does not show up as phase error.
    """
    if result.frame_count == 0 or len(true_times) == 0:
        return _EMPTY_PHASE

    errors_frac: List[float] = []
    errors_ms: List[float] = []
    for t_true in true_times:
        if t_true < warmup_s or t_true > result.frame_times[-1]:
            continue
        i = int(np.argmin(np.abs(result.frame_times - t_true)))
        bpm = float(result.engine_bpm[i])
        if bpm <= 0:
            continue
        cycle_s = (60.0 / bpm) / max(1e-9, cycles_per_beat)
        phase = float(phases[i]) + (t_true - float(result.frame_times[i])) / cycle_s
        frac = abs(((phase + 0.5) % 1.0) - 0.5)
        errors_frac.append(frac)
        errors_ms.append(frac * cycle_s * 1000.0)

    if not errors_frac:
        return _EMPTY_PHASE
    return PhaseError(
        count=len(errors_frac),
        mean_ms=float(np.mean(errors_ms)),
        worst_ms=float(np.max(errors_ms)),
        mean_fraction=float(np.mean(errors_frac)),
        worst_fraction=float(np.max(errors_frac)),
    )


def beat_phase_error(result: RunResult, track: SyntheticTrack, warmup_s: float = 6.0) -> PhaseError:
    """Engine beat phase against the true beat grid."""
    return _phase_error(result, track.beat_times, result.beat_phase, 1.0, warmup_s)


def bar_phase_error(result: RunResult, track: SyntheticTrack, warmup_s: float = 6.0) -> PhaseError:
    """Engine bar phase against the true downbeats (one cycle = four beats)."""
    return _phase_error(result, track.downbeat_times, result.bar_phase, 0.25, warmup_s)


def detected_beat_error(result: RunResult, track: SyntheticTrack, warmup_s: float = 6.0) -> PhaseError:
    """Timing of the analyser's own beat events against the true grid.

    Separate from the engine phase on purpose: this is the detector's error,
    and the engine's phase error can be far larger even when this is small.
    """
    true_times = track.beat_times
    detected = result.detected_beat_times
    if len(true_times) == 0 or len(detected) == 0:
        return _EMPTY_PHASE

    beat_s = 60.0 / track.bpm if track.bpm > 0 else 0.5
    errors_ms: List[float] = []
    for t_true in true_times:
        if t_true < warmup_s:
            continue
        delta = np.min(np.abs(detected - t_true))
        errors_ms.append(float(delta) * 1000.0)
    if not errors_ms:
        return _EMPTY_PHASE
    return PhaseError(
        count=len(errors_ms),
        mean_ms=float(np.mean(errors_ms)),
        worst_ms=float(np.max(errors_ms)),
        mean_fraction=float(np.mean(errors_ms)) / (beat_s * 1000.0),
        worst_fraction=float(np.max(errors_ms)) / (beat_s * 1000.0),
    )


def section_timeline(result: RunResult) -> List[Tuple[float, str]]:
    """Section decisions as (time, section) transitions, ready to diff."""
    timeline: List[Tuple[float, str]] = []
    previous: Optional[str] = None
    for t, section in zip(result.frame_times, result.sections):
        if section != previous:
            timeline.append((round(float(t), 3), section))
            previous = section
    return timeline


def section_names(result: RunResult) -> List[str]:
    """The order sections were visited in, without the timestamps."""
    return [name for _, name in section_timeline(result)]


def section_occupancy(result: RunResult) -> Dict[str, float]:
    """Fraction of the run spent in each section."""
    total = len(result.sections)
    if total == 0:
        return {}
    counts: Dict[str, int] = {}
    for name in result.sections:
        counts[name] = counts.get(name, 0) + 1
    return {k: round(v / total, 4) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}


def section_agreement(a: RunResult, b: RunResult) -> float:
    """Fraction of frames on which two runs made the same section decision.

    Frame-wise rather than transition-wise on purpose: it tolerates a boundary
    landing a frame or two apart, which is the "small tolerance at boundaries"
    a gain-invariance check is allowed, while still going to pieces if the two
    runs spend the show in different sections.
    """
    n = min(len(a.sections), len(b.sections))
    if n == 0:
        return 0.0
    matches = sum(1 for i in range(n) if a.sections[i] == b.sections[i])
    return matches / float(n)


def section_changes_per_minute(result: RunResult) -> float:
    timeline = section_timeline(result)
    minutes = result.duration_s / 60.0
    if minutes <= 0:
        return 0.0
    # The first entry is the section the run started in, not a change.
    return (max(0, len(timeline) - 1)) / minutes


def shortest_section_hold_s(result: RunResult) -> float:
    timeline = section_timeline(result)
    if len(timeline) < 2:
        return float(result.duration_s)
    holds = [timeline[i + 1][0] - timeline[i][0] for i in range(len(timeline) - 1)]
    return float(min(holds)) if holds else float(result.duration_s)


@dataclass(frozen=True)
class DynamicRange:
    p5: float
    p50: float
    p95: float

    @property
    def spread(self) -> float:
        return self.p95 - self.p5

    def as_dict(self) -> dict:
        return {
            "p5": round(self.p5, 4),
            "p50": round(self.p50, 4),
            "p95": round(self.p95, 4),
            "p95_minus_p5": round(self.spread, 4),
        }


def dimmer_dynamic_range(result: RunResult, per_fixture: bool = True) -> DynamicRange:
    """p5/p50/p95 of emitted intensity across the track.

    Pooled over every fixture on every frame by default: that is the
    distribution of light the room actually receives. `per_fixture=False`
    pools the rig mean instead, which is what an audience member's overall
    impression of level tracks.
    """
    data = result.intensity.reshape(-1) if per_fixture else result.rig_mean
    if data.size == 0:
        return DynamicRange(float("nan"), float("nan"), float("nan"))
    p5, p50, p95 = np.percentile(data, [5, 50, 95])
    return DynamicRange(float(p5), float(p50), float(p95))


@dataclass(frozen=True)
class AccentCounts:
    bumps: int
    blackouts: int
    strobe_flashes: int
    duration_s: float

    @property
    def total(self) -> int:
        return self.bumps + self.blackouts + self.strobe_flashes

    @property
    def per_minute(self) -> float:
        minutes = self.duration_s / 60.0
        return (self.total / minutes) if minutes > 0 else 0.0

    def as_dict(self) -> dict:
        return {
            "bumps": self.bumps,
            "blackouts": self.blackouts,
            "strobe_flashes": self.strobe_flashes,
            "total": self.total,
            "per_minute": round(self.per_minute, 2),
        }


def accent_events(
    result: RunResult,
    *,
    rise: float = 0.25,
    peak_floor: float = 0.60,
    window_s: float = 0.10,
    fall_to: float = 0.05,
    fall_from: float = 0.35,
    refractory_s: float = 0.15,
) -> AccentCounts:
    """Bumps, blackouts and strobe flashes visible on the wire.

    An accent is something the audience registers as a discrete event, so a
    bump has to be both fast and big: the rig has to climb `rise` within
    `window_s` *and* arrive above `peak_floor`. Rate alone is not enough,
    because a running chase swings the rig level continuously and would
    otherwise be counted as an accent several times a second.
    """
    rig = result.rig_mean
    times = result.frame_times
    if rig.size < 2:
        return AccentCounts(0, 0, 0, result.duration_s)

    span = max(1, int(round(window_s * result.fps)))
    bumps = 0
    blackouts = 0
    last_bump = -1e9
    last_black = -1e9
    for i in range(1, len(rig)):
        t = times[i]
        floor = float(np.min(rig[max(0, i - span):i]))
        if rig[i] >= peak_floor and (rig[i] - floor) >= rise and (t - last_bump) >= refractory_s:
            bumps += 1
            last_bump = t
        if rig[i] <= fall_to and rig[i - 1] >= fall_from and (t - last_black) >= refractory_s:
            blackouts += 1
            last_black = t

    flashes = 0
    previous = False
    for flag in result.white_flash:
        if flag and not previous:
            flashes += 1
        previous = bool(flag)

    return AccentCounts(bumps, blackouts, flashes, result.duration_s)


def largest_frame_rise(result: RunResult) -> float:
    """Biggest one-frame jump in rig level anywhere in the run.

    A continuous companion to the accent count: when accents are switched off
    entirely the count is zero on every track, and this still separates a rig
    that lifts a little from one that never moves.
    """
    rig = result.rig_mean
    if rig.size < 2:
        return 0.0
    return float(np.max(np.diff(rig)))


def strobe_frame_fraction(result: RunResult) -> float:
    """Fraction of frames with at least one fixture flashing full white."""
    if result.white_flash.size == 0:
        return 0.0
    return float(np.count_nonzero(result.white_flash)) / float(result.white_flash.size)


def white_flash_times(result: RunResult) -> np.ndarray:
    """Time of every rising edge into a full-white flash."""
    times = []
    previous = False
    for t, flag in zip(result.frame_times, result.white_flash):
        if flag and not previous:
            times.append(float(t))
        previous = bool(flag)
    return np.asarray(times, dtype=np.float64)


def peak_flash_rate_hz(result: RunResult, window_s: float = 1.0) -> float:
    """Highest white-flash rate in any window of `window_s`.

    A rendered frame is the finest thing the wire can show, so a 60 fps capture
    can only resolve alternation up to 30 Hz; this measures what an audience
    would actually be exposed to at the frame rate the engine runs.
    """
    edges = white_flash_times(result)
    if edges.size == 0:
        return 0.0
    best = 0
    for start in edges:
        best = max(best, int(np.count_nonzero((edges >= start) & (edges < start + window_s))))
    return best / float(window_s)


def drop_latency_ms(
    result: RunResult,
    track: SyntheticTrack,
    *,
    step: float = 0.15,
    pre_window_s: float = 1.0,
) -> Optional[float]:
    """Milliseconds from the true drop to the first materially brighter frame.

    "Material" is a step of `step` in mean rig level above the second before
    the drop. None means the output never changed by that much, which is the
    honest reading of a drop that does not land.
    """
    t_drop = track.drop_time
    if t_drop is None or result.frame_count == 0:
        return None
    times = result.frame_times
    rig = result.rig_mean
    pre_mask = (times >= t_drop - pre_window_s) & (times < t_drop)
    if not np.any(pre_mask):
        return None
    baseline = float(np.mean(rig[pre_mask]))
    for i in range(len(times)):
        if times[i] < t_drop:
            continue
        if rig[i] >= baseline + step:
            return float(times[i] - t_drop) * 1000.0
    return None


def drop_intensity_step(
    result: RunResult,
    track: SyntheticTrack,
    *,
    pre_window_s: float = 1.0,
    post_window_s: float = 2.0,
) -> Optional[float]:
    """How much brighter the rig actually gets when the drop lands.

    Always defined, so it stays comparable when `drop_latency_ms` reports None
    because the output never moved far enough to count as landing.
    """
    t_drop = track.drop_time
    if t_drop is None or result.frame_count == 0:
        return None
    times = result.frame_times
    rig = result.rig_mean
    pre = (times >= t_drop - pre_window_s) & (times < t_drop)
    post = (times >= t_drop) & (times < t_drop + post_window_s)
    if not np.any(pre) or not np.any(post):
        return None
    return float(np.max(rig[post]) - np.mean(rig[pre]))


def drop_section_latency_ms(
    result: RunResult,
    track: SyntheticTrack,
    targets: Sequence[str] = ("drop",),
) -> Optional[float]:
    """Milliseconds from the true drop to the section decision naming it."""
    t_drop = track.drop_time
    if t_drop is None:
        return None
    wanted = {t.lower() for t in targets}
    for t, section in zip(result.frame_times, result.sections):
        if t >= t_drop and section in wanted:
            return float(t - t_drop) * 1000.0
    return None


def energy_percentiles(result: RunResult) -> Dict[str, float]:
    """What the engine's threshold ladder is actually being fed."""
    if result.chunk_energy.size == 0:
        return {}
    p5, p50, p95 = np.percentile(result.chunk_energy, [5, 50, 95])
    return {
        "energy_p5": round(float(p5), 4),
        "energy_p50": round(float(p50), 4),
        "energy_p95": round(float(p95), 4),
        "energy_max": round(float(np.max(result.chunk_energy)), 4),
        "rms_p50": round(float(np.median(result.chunk_rms)), 5),
    }


def bpm_estimate(result: RunResult, warmup_s: float = 6.0) -> float:
    """Median reported BPM after the detector has had time to settle."""
    mask = result.chunk_times >= warmup_s
    values = result.chunk_bpm[mask]
    if values.size == 0:
        return float("nan")
    return float(np.median(values))


def summarise(result: RunResult, track: SyntheticTrack, warmup_s: float = 6.0) -> dict:
    """Every headline metric for one run, as a flat dictionary."""
    dyn = dimmer_dynamic_range(result)
    accents = accent_events(result)
    summary = {
        "track": result.track_name,
        "gain_db": result.gain_db,
        "duration_s": round(result.duration_s, 2),
        "frames": result.frame_count,
        "fixtures": len(result.fixture_ids),
        "bpm_true": track.bpm,
        "bpm_reported": round(bpm_estimate(result, warmup_s), 1),
        "beat_phase_error": beat_phase_error(result, track, warmup_s).as_dict(),
        "bar_phase_error": bar_phase_error(result, track, warmup_s).as_dict(),
        "detected_beat_error": detected_beat_error(result, track, warmup_s).as_dict(),
        "sections": section_timeline(result),
        "section_occupancy": section_occupancy(result),
        "section_changes_per_min": round(section_changes_per_minute(result), 2),
        "shortest_section_hold_s": round(shortest_section_hold_s(result), 3),
        "dynamic_range": dyn.as_dict(),
        "accents": accents.as_dict(),
        "largest_frame_rise": round(largest_frame_rise(result), 4),
        "strobe_frame_fraction": round(strobe_frame_fraction(result), 5),
        "normalised_energy_published": result.normalised_energy is not None,
    }
    summary.update(energy_percentiles(result))
    if track.drop_time is not None:
        latency = drop_latency_ms(result, track)
        step = drop_intensity_step(result, track)
        summary["drop_latency_ms"] = None if latency is None else round(latency, 1)
        summary["drop_section_latency_ms"] = drop_section_latency_ms(result, track)
        summary["drop_intensity_step"] = None if step is None else round(step, 4)
    return summary


def format_summary(summary: dict) -> str:
    """Readable block for a report or a -s test run."""
    lines = [f"--- {summary['track']} ({summary['gain_db']:+g} dB) ---"]
    for key, value in summary.items():
        if key in ("track", "gain_db"):
            continue
        if key == "sections":
            rendered = " -> ".join(f"{t:.2f}s {name}" for t, name in value)
            lines.append(f"  {key}: {rendered}")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)
