"""
Section-Aware Intensity and Dynamic Range Manager
Handles song structure transitions with professional timing.

Features:
- Section-aware intensity (verse 50-70%, chorus 80-100%, drop 100%, breakdown 20-40%)
- Dynamic range management (prevents clipping and muddy looks)
- Anticipation timing (pre-loads next look 1-2 bars ahead)
- Build-up progressive ramp
- Section detection from audio energy contour

WHICH SECTION DETECTOR IS ACTUALLY LIVE (read before trusting any of them):

* `EffectsEngine._rebuild_update_intent` is the one that decides the section the
  venue sees. It is a threshold ladder with no hysteresis, and it still has the
  ordering bug that makes `chorus` unreachable (the `e > 0.58` buildup branch is
  tested before the `e > 0.64` chorus branch).
* `EffectsEngine._update_busker_section_intent` and the fallback ladder in
  `_update_fixtures_rebuild` are also live on their respective paths.
* `StreamingSectionDetector` below is the good detector — multi-rate EMA
  novelty, boundary probability, debounce, minimum hold, drop refractory — and
  it is NOT wired into the renderer. `SectionManager.update_section_from_audio`
  currently has no caller in `app/`. `MusicStructureAnalyzer` uses the same
  class for its anticipation signal and no longer classifies sections itself.

So promoting it is still outstanding work; do not read the presence of this
class as evidence that the show runs on it.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable


# Shared musical timing rules used by section/effect systems.
ALLOWED_MUSICAL_BOUNDARIES: Tuple[int, ...] = (4, 8, 16)
IMPACT_SECTIONS = {"drop"}

# The section vocabulary the live renderer understands. Anything outside this
# set falls through the renderer's section ladder to its defaults, so the
# detector must never emit a name that is not here.
LIVE_SECTION_NAMES: Tuple[str, ...] = ("breakdown", "verse", "buildup", "chorus", "drop")


def is_downbeat(beat_number: int) -> bool:
    """Return True when beat number represents a bar downbeat."""
    return beat_number > 0 and beat_number % 4 == 1


def next_musical_boundary_bar(completed_bars: int) -> int:
    """Get next allowed commit bar based on 4/8/16 phrase boundaries."""
    candidate = completed_bars + 1
    while not any(candidate % bars == 0 for bars in ALLOWED_MUSICAL_BOUNDARIES):
        candidate += 1
    return candidate


def bars_until_boundary(completed_bars: int) -> int:
    """How many bars remain until the next allowed boundary."""
    return max(0, next_musical_boundary_bar(completed_bars) - completed_bars)


def is_impact_event(section_name: str) -> bool:
    """Impact sections bypass normal boundary waiting."""
    return section_name.lower() in IMPACT_SECTIONS


@dataclass
class SectionDecision:
    """One frame of detector output."""

    section: str = "verse"
    changed: bool = False
    level: float = 0.5
    trend: float = 0.0
    bass_level: float = 0.5
    flux_level: float = 0.5
    drop_impact: bool = False
    on_boundary: bool = False


class StreamingSectionDetector:
    """Causal section detector: relative dynamics, hysteresis, bar-aligned commits.

    Every feature is measured against the running centre and spread of the same
    feature on this track, so the classification is invariant to a change of
    *gain*: the same performance 12 dB quieter lands in the same sections, on
    the same frames. Absolute energy thresholds are what put the retired ladder
    in one section all night, because `min(1.0, rms * 2)` on mastered programme
    material sits around 0.07.

    That invariance is multiplicative, and it is not invariance to an arbitrary
    remap of the input. `_rel`'s scale floor is a fraction of the centre, which
    is the right floor in a domain where zero means silence and doubling the
    input doubles every excursion. Fed a loudness-normalised value instead -
    an affine map of decibels, which parks programme around 0.5 whatever it
    weighs - that floor reads the DC pedestal as "this track's normal excursion
    is large" and every deviation term shrinks about fivefold: measured on the
    drop track, the rise the drop test needs fell from 1.02 to 0.25 and no
    frame in the run satisfied it. Feed this the raw energy.

    Two structural rules matter more than the constants:

    * Buildup is defined by a *rise* and chorus by a *sustain*, so the two
      cannot shadow each other whichever order they are tested in. The retired
      ladder made `chorus` unreachable precisely because both branches tested
      level alone and buildup came first.
    * The centre nearly stops chasing the level while the two are far apart, so
      a long chorus is not dragged back to mid scale and demoted to a verse.
      That guard is time limited, because a centre permanently held behind the
      level keeps itself held behind the level.

    Commits are held until a bar line. Phrase (4/8/16 bar) alignment is
    deliberately not enforced: at 128 BPM the wait would be up to 15 s, which is
    longer than the whole drop-latency budget. A drop is an impact event and
    bypasses the wait entirely.
    """

    # Feature smoothing, seconds. The level constant has to be at least a bar
    # or the per-kick swing of a steady groove reads as a section change.
    _TAU_LEVEL = 2.2
    _TAU_FAST = 0.18        # transient level, for impact detection
    _TAU_CENTRE = 30.0      # what "normal" means on this track
    _TAU_DEV = 20.0         # typical excursion away from that centre
    _TAU_LAG = 6.0          # lagged level, for rise detection
    _TAU_RISE_FAST = 1.0
    _TAU_RISE_SLOW = 3.5

    # Deviation scale. The relative term is what makes the detector gain
    # invariant; the absolute term only stops the division exploding near
    # digital silence.
    _MIN_REL_DEV = 0.45
    _ABS_DEV_FLOOR = 2e-3
    _SILENCE_LEVEL = 1.5e-3

    # Deviations beyond this many scale units read as fully high/low.
    _Z_FULL = 1.6

    # While the level is this far from the centre the centre nearly stops
    # chasing it, so a long chorus is not dragged back to mid scale and demoted.
    _ANTI_PUMP_Z = 0.9
    _ANTI_PUMP_FACTOR = 0.22
    _ANTI_PUMP_MAX_S = 20.0

    # Commit machinery, seconds unless named otherwise.
    _WARMUP_S = 4.0
    _DWELL_S = 0.55
    _MIN_HOLD_BARS = 2.0
    _MIN_HOLD_S = 1.4
    _BOUNDARY_WAIT_BARS = 1.5
    _BOUNDARY_WAIT_MAX_S = 3.0
    _IMPACT_MIN_HOLD_S = 0.8
    _DROP_REFRACTORY_S = 4.0
    _DROP_HOLD_S = 2.6

    # Classification thresholds on the 0..1 relative level, with the band the
    # detector is already in widened so it does not flap on its own edge.
    _LOW = 0.24
    _LOW_STICKY = 0.32
    _HIGH = 0.66
    _HIGH_STICKY = 0.58
    _BUILDUP_MIN_LEVEL = 0.34
    _CHORUS_MIN_BASS = 0.42
    _DROP_MIN_LEVEL = 0.62
    _DROP_MIN_BASS = 0.55
    _DROP_MIN_FAST_Z = 1.4
    _DROP_MIN_RISE = 0.7
    # Absolute, in the analyser's normalised-loudness domain: 0.5 is this
    # material's own running reference and the scale is 30 dB wide, so this is
    # "at least 3 dB above what this track has been averaging". A steady noise
    # floor normalises to exactly 0.5 whatever its level, so it never clears it.
    _DROP_MIN_PROGRAMME = 0.60

    # Rise is in deviation units, not in level units: the level saturates on any
    # real build and a saturated level has no slope left to read a build from.
    # It is averaged because a steady groove swings the level once a bar, and an
    # instantaneous slope cannot tell that apart from a build.
    _RISE = 0.55
    _RISE_STICKY = 0.32
    _RISE_FAST_FACTOR = 1.8
    _RISE_SETTLED = 0.35

    # A build is a climb towards a peak, so it cannot start inside one.
    _POST_DROP_NO_BUILD_S = 12.0

    # Sections a drop can be entered from. Without this a sustained drop
    # re-triggers itself every refractory period and reads as flapping.
    _DROP_FROM = ("breakdown", "verse", "buildup")

    def __init__(self, now: Optional[float] = None):
        self.reset(now)

    def reset(self, now: Optional[float] = None) -> None:
        self._section = "verse"
        self._candidate = "verse"
        self._last_beat_number = -1
        self._rebase(time.time() if now is None else float(now))
        self._seeded = False

        self._level = 0.0
        self._fast = 0.0
        self._centre = 0.0
        self._dev = 0.0
        self._lag = 0.0
        self._rise_fast = 0.0
        self._rise_slow = 0.0
        self._bass_level = 0.0
        self._bass_fast = 0.0
        self._bass_centre = 0.0
        self._bass_dev = 0.0
        self._flux_level = 0.0
        self._flux_centre = 0.0
        self._flux_dev = 0.0

        self._decision = SectionDecision()

    def _rebase(self, t: float) -> None:
        """Restart every timer on `t`, keeping the current section."""
        self._seeded = True
        self._start_time = t
        self._last_time = t
        self._section_since = t
        self._candidate_since = t
        self._eligible_since: Optional[float] = None
        self._z_high_since: Optional[float] = None
        self._drop_until = t - 1e6
        self._last_drop_time = t - 1e6

    @property
    def section(self) -> str:
        return self._section

    @property
    def decision(self) -> SectionDecision:
        return self._decision

    @staticmethod
    def _finite(value: float, fallback: float = 0.0) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return fallback
        if v != v or v in (float("inf"), float("-inf")):
            return fallback
        return v

    @staticmethod
    def _clamp01(value: float) -> float:
        return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)

    @staticmethod
    def _alpha(dt: float, tau: float) -> float:
        return dt / (tau + dt)

    def _rel(self, value: float, centre: float, dev: float) -> float:
        scale = max(self._ABS_DEV_FLOOR, self._MIN_REL_DEV * centre, dev)
        z = (value - centre) / scale / self._Z_FULL
        return self._clamp01(0.5 + 0.5 * max(-1.0, min(1.0, z)))

    def update(
        self,
        delta_time: Optional[float] = None,
        *,
        energy: float = 0.0,
        bass: float = 0.0,
        spectral_flux: float = 0.0,
        is_beat: bool = False,
        beat_number: int = 0,
        bpm: float = 128.0,
        is_downbeat_event: Optional[bool] = None,
        programme_level: Optional[float] = None,
        now: Optional[float] = None,
    ) -> SectionDecision:
        """Advance one frame and return the section to render.

        Runs inside the 60 fps update path, so it swallows its own arithmetic
        failures and keeps showing the previous section rather than going dark.
        """
        try:
            return self._update(
                delta_time,
                energy=energy,
                bass=bass,
                spectral_flux=spectral_flux,
                is_beat=is_beat,
                beat_number=beat_number,
                bpm=bpm,
                is_downbeat_event=is_downbeat_event,
                programme_level=programme_level,
                now=now,
            )
        except Exception:
            self._decision = SectionDecision(
                section=self._section,
                changed=False,
                level=self._decision.level,
                trend=self._decision.trend,
                bass_level=self._decision.bass_level,
                flux_level=self._decision.flux_level,
            )
            return self._decision

    def _update(
        self,
        delta_time: Optional[float],
        *,
        energy: float,
        bass: float,
        spectral_flux: float,
        is_beat: bool,
        beat_number: int,
        bpm: float,
        is_downbeat_event: Optional[bool],
        programme_level: Optional[float],
        now: Optional[float],
    ) -> SectionDecision:
        t = time.time() if now is None else self._finite(now, time.time())

        energy = max(0.0, self._finite(energy))
        bass = max(0.0, self._finite(bass))
        flux = max(0.0, self._finite(spectral_flux))
        bpm = self._finite(bpm, 128.0)
        bar_s = (4.0 * 60.0) / max(50.0, min(220.0, bpm if bpm > 0 else 128.0))

        # The manager is constructed long before the first audio frame and the
        # clock can be swapped underneath it, so the timeline is seeded here
        # rather than in __init__.
        if not self._seeded or t < self._last_time - 0.5 or t > self._last_time + 5.0:
            self._rebase(t)
            self._level = self._fast = self._centre = self._lag = energy
            self._bass_level = self._bass_fast = self._bass_centre = bass
            self._flux_level = self._flux_centre = flux
            self._rise_fast = self._rise_slow = 0.0

        dt = self._finite(delta_time, 0.0) if delta_time is not None else (t - self._last_time)
        if not (0.0 < dt <= 0.25):
            dt = 1.0 / 60.0
        self._last_time = t

        self._level += (energy - self._level) * self._alpha(dt, self._TAU_LEVEL)
        self._fast += (energy - self._fast) * self._alpha(dt, self._TAU_FAST)
        self._bass_level += (bass - self._bass_level) * self._alpha(dt, self._TAU_LEVEL)
        self._bass_fast += (bass - self._bass_fast) * self._alpha(dt, self._TAU_FAST)
        self._flux_level += (flux - self._flux_level) * self._alpha(dt, self._TAU_LEVEL)

        scale = max(self._ABS_DEV_FLOOR, self._MIN_REL_DEV * self._centre, self._dev)
        warm = (t - self._start_time) >= self._WARMUP_S
        if not warm:
            # The smoothed level climbs out of the seed during the first
            # seconds. Averaging that ramp into the centre would bias every
            # later comparison upwards for the rest of the track.
            self._centre = self._level
            self._lag = self._level
            self._bass_centre = self._bass_level
            self._flux_centre = self._flux_level
            self._dev = self._bass_dev = self._flux_dev = 0.0
            self._rise_fast = self._rise_slow = 0.0
        else:
            # The centre is the running mean since warm-up until the track is
            # older than the centre time constant, then a plain EMA.
            age = max(1e-3, t - self._start_time - self._WARMUP_S)
            centre_tau = min(self._TAU_CENTRE, max(1.0, age))
            dev_tau = min(self._TAU_DEV, max(1.0, age))

            self._lag += (self._level - self._lag) * self._alpha(dt, self._TAU_LAG)

            z = (self._level - self._centre) / scale
            if abs(z) >= self._ANTI_PUMP_Z:
                if self._z_high_since is None:
                    self._z_high_since = t
                # Time limited: an unbounded guard is self-reinforcing, because
                # a centre held behind the level keeps |z| high forever.
                pump = (
                    self._ANTI_PUMP_FACTOR
                    if (t - self._z_high_since) < self._ANTI_PUMP_MAX_S
                    else 1.0
                )
            else:
                self._z_high_since = None
                pump = 1.0

            self._centre += (self._level - self._centre) * self._alpha(dt, centre_tau) * pump
            self._dev += (abs(self._level - self._centre) - self._dev) * self._alpha(dt, dev_tau)
            self._bass_centre += (
                self._bass_level - self._bass_centre
            ) * self._alpha(dt, centre_tau)
            self._bass_dev += (
                abs(self._bass_level - self._bass_centre) - self._bass_dev
            ) * self._alpha(dt, dev_tau)
            self._flux_centre += (
                self._flux_level - self._flux_centre
            ) * self._alpha(dt, centre_tau)
            self._flux_dev += (
                abs(self._flux_level - self._flux_centre) - self._flux_dev
            ) * self._alpha(dt, dev_tau)

            scale = max(self._ABS_DEV_FLOOR, self._MIN_REL_DEV * self._centre, self._dev)
            raw_rise = (self._level - self._lag) / scale
            self._rise_fast += (raw_rise - self._rise_fast) * self._alpha(dt, self._TAU_RISE_FAST)
            self._rise_slow += (raw_rise - self._rise_slow) * self._alpha(dt, self._TAU_RISE_SLOW)

        # Flux is measured and published but not gated on: on this material it
        # carries nothing the level does not already say. Left in so the next
        # pass can see it rather than having to re-derive it.
        lvl = self._rel(self._level, self._centre, self._dev)
        blvl = self._rel(self._bass_level, self._bass_centre, self._bass_dev)
        bfast = self._rel(self._bass_fast, self._bass_centre, self._bass_dev)
        flvl = self._rel(self._flux_level, self._flux_centre, self._flux_dev)
        fast_z = (self._fast - self._centre) / scale

        beat_number = int(self._finite(beat_number, 0))
        beat_event = bool(is_beat) and beat_number > 0 and beat_number != self._last_beat_number
        if beat_event:
            self._last_beat_number = beat_number
        if is_downbeat_event is None:
            downbeat_event = beat_event and is_downbeat(beat_number)
        else:
            downbeat_event = bool(is_downbeat_event) and beat_event

        current = self._section

        # Every other term here is relative, so all of them are satisfiable by
        # a small excursion in quiet material. A drop is the one decision that
        # reaches the strobe, and an accent in a quiet passage is worse than no
        # accent, so it also has to be loud in absolute programme terms. That
        # judgement needs a playback-level-invariant measure, which is exactly
        # what the analyser's normalised loudness is; a source that publishes
        # none abstains rather than blocking.
        loud_enough = (
            programme_level is None
            or self._finite(programme_level, 1.0) >= self._DROP_MIN_PROGRAMME
        )

        drop_impact = (
            warm
            and beat_event
            and current in self._DROP_FROM
            and lvl >= self._DROP_MIN_LEVEL
            and bfast >= self._DROP_MIN_BASS
            and fast_z >= self._DROP_MIN_FAST_Z
            and self._rise_fast >= self._DROP_MIN_RISE
            and loud_enough
            and (t - self._last_drop_time) >= self._DROP_REFRACTORY_S
            and (t - self._section_since) >= self._IMPACT_MIN_HOLD_S
        )

        if self._centre <= self._SILENCE_LEVEL and self._level <= self._SILENCE_LEVEL:
            target = "breakdown"
        elif t < self._drop_until:
            target = "drop"
        else:
            low = self._LOW_STICKY if current == "breakdown" else self._LOW
            high = self._HIGH_STICKY if current == "chorus" else self._HIGH
            rise_gate = self._RISE_STICKY if current == "buildup" else self._RISE
            # Inside a peak nothing can be building, and a level still climbing
            # out of the drop is the drop resolving, not a new section.
            in_peak = (t - self._last_drop_time) < self._POST_DROP_NO_BUILD_S
            rising = (
                self._rise_slow >= rise_gate
                or self._rise_fast >= rise_gate * self._RISE_FAST_FACTOR
            ) and not in_peak
            settled = in_peak or self._rise_fast < self._RISE_SETTLED
            if lvl <= low:
                target = "breakdown"
            elif rising and lvl >= self._BUILDUP_MIN_LEVEL:
                target = "buildup"
            elif lvl >= high and blvl >= self._CHORUS_MIN_BASS and settled:
                target = "chorus"
            else:
                target = "verse"

        if drop_impact:
            target = "drop"

        if target != self._candidate:
            self._candidate = target
            self._candidate_since = t

        changed = False
        if target == current:
            self._eligible_since = None
        elif not warm:
            self._eligible_since = None
        elif drop_impact and is_impact_event(target):
            changed = self._commit(target, t)
        else:
            dwell_ok = (t - self._candidate_since) >= self._DWELL_S
            hold_ok = (t - self._section_since) >= max(
                self._MIN_HOLD_S, self._MIN_HOLD_BARS * bar_s
            )
            if dwell_ok and hold_ok:
                if self._eligible_since is None:
                    self._eligible_since = t
                waited = t - self._eligible_since
                wait_cap = min(self._BOUNDARY_WAIT_MAX_S, self._BOUNDARY_WAIT_BARS * bar_s)
                if downbeat_event or waited >= wait_cap:
                    changed = self._commit(target, t)
            else:
                self._eligible_since = None

        self._decision = SectionDecision(
            section=self._section,
            changed=changed,
            level=lvl,
            trend=self._rise_slow,
            bass_level=blvl,
            flux_level=flvl,
            drop_impact=drop_impact,
            on_boundary=downbeat_event,
        )
        return self._decision

    def _commit(self, section: str, t: float) -> bool:
        if section not in LIVE_SECTION_NAMES or section == self._section:
            return False
        self._section = section
        self._section_since = t
        self._eligible_since = None
        if section == "drop":
            self._last_drop_time = t
            self._drop_until = t + self._DROP_HOLD_S
        return True

    def debug(self) -> Dict[str, float | str | bool]:
        d = self._decision
        return {
            "section": d.section,
            "level": round(d.level, 4),
            "trend": round(d.trend, 4),
            "bass_level": round(d.bass_level, 4),
            "flux_level": round(d.flux_level, 4),
            "drop_impact": bool(d.drop_impact),
            "centre": round(self._centre, 5),
            "dev": round(self._dev, 5),
        }


class SongSection(Enum):
    """Song structure sections."""
    INTRO = "intro"
    VERSE = "verse"
    PRE_CHORUS = "pre_chorus"
    CHORUS = "chorus"
    DROP = "drop"
    BREAKDOWN = "breakdown"
    BRIDGE = "bridge"
    OUTRO = "outro"
    BUILDUP = "buildup"
    UNKNOWN = "unknown"


@dataclass
class SectionConfig:
    """Configuration for a specific section."""
    # Intensity range (min, max as 0-1)
    intensity_range: Tuple[float, float] = (0.5, 0.7)

    # Movement energy multiplier
    movement_energy: float = 0.5

    # Color saturation preference (0-1)
    color_saturation: float = 0.7

    # Whether strobe is allowed in this section
    strobe_allowed: bool = False

    # Beat reactivity (how much intensity follows beats, 0-1)
    beat_reactivity: float = 0.5

    # Dimmer floor (never go below this)
    dimmer_floor: float = 0.0


# Default section configurations
DEFAULT_SECTION_CONFIGS: Dict[SongSection, SectionConfig] = {
    SongSection.INTRO: SectionConfig(
        intensity_range=(0.3, 0.5),
        movement_energy=0.2,
        color_saturation=0.5,
        strobe_allowed=False,
        beat_reactivity=0.3,
        dimmer_floor=0.0,
    ),
    SongSection.VERSE: SectionConfig(
        intensity_range=(0.6, 0.85),
        movement_energy=0.4,
        color_saturation=0.7,
        strobe_allowed=False,
        beat_reactivity=0.65,
        dimmer_floor=0.0,
    ),
    SongSection.PRE_CHORUS: SectionConfig(
        intensity_range=(0.7, 0.95),
        movement_energy=0.6,
        color_saturation=0.8,
        strobe_allowed=False,
        beat_reactivity=0.72,
        dimmer_floor=0.0,
    ),
    SongSection.CHORUS: SectionConfig(
        intensity_range=(0.8, 1.0),
        movement_energy=0.8,
        color_saturation=0.9,
        strobe_allowed=True,
        beat_reactivity=0.7,
        dimmer_floor=0.0,
    ),
    SongSection.DROP: SectionConfig(
        intensity_range=(0.9, 1.0),
        movement_energy=1.0,
        color_saturation=1.0,
        strobe_allowed=True,
        beat_reactivity=0.9,
        dimmer_floor=0.0,
    ),
    SongSection.BREAKDOWN: SectionConfig(
        intensity_range=(0.25, 0.55),
        movement_energy=0.15,
        color_saturation=0.4,
        strobe_allowed=False,
        beat_reactivity=0.3,
        dimmer_floor=0.0,
    ),
    SongSection.BRIDGE: SectionConfig(
        intensity_range=(0.4, 0.6),
        movement_energy=0.4,
        color_saturation=0.6,
        strobe_allowed=False,
        beat_reactivity=0.4,
        dimmer_floor=0.0,
    ),
    SongSection.OUTRO: SectionConfig(
        intensity_range=(0.2, 0.4),
        movement_energy=0.15,
        color_saturation=0.4,
        strobe_allowed=False,
        beat_reactivity=0.2,
        dimmer_floor=0.0,
    ),
    SongSection.BUILDUP: SectionConfig(
        intensity_range=(0.4, 0.9),
        movement_energy=0.7,
        color_saturation=0.8,
        strobe_allowed=True,
        beat_reactivity=0.7,
        dimmer_floor=0.0,
    ),
    SongSection.UNKNOWN: SectionConfig(
        intensity_range=(0.55, 0.8),
        movement_energy=0.5,
        color_saturation=0.7,
        strobe_allowed=False,
        beat_reactivity=0.6,
        dimmer_floor=0.0,
    ),
}


@dataclass
class SectionTransition:
    """Tracks an in-progress section transition."""
    from_section: SongSection
    to_section: SongSection
    start_time: float
    duration: float  # seconds
    progress: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.progress >= 1.0


class SectionManager:
    """
    Manages song section state and provides intensity/parameter
    modulation based on current section.
    """

    def __init__(self, bpm: float = 128.0):
        self._current_section = SongSection.UNKNOWN
        self._previous_section = SongSection.UNKNOWN
        self._section_configs = dict(DEFAULT_SECTION_CONFIGS)

        # Timing
        self._bpm = bpm
        self._section_start_time = time.time()
        self._bars_in_section = 0
        self._beat_count = 0

        # Transition state
        self._transition: Optional[SectionTransition] = None
        self._crossfade_duration_bars = 0.125

        # Anticipation (pre-loading next look)
        self._anticipation_bars = 1.0
        self._pending_section: Optional[SongSection] = None
        self._pending_section_time: Optional[float] = None

        # Build-up ramp state
        self._buildup_start_time: Optional[float] = None
        self._buildup_duration: float = 8.0  # beats
        self._buildup_progress: float = 0.0

        # Dynamic range state
        self._current_intensity = 0.5
        self._target_intensity = 0.5
        self._intensity_smoothing = 0.1

        # Energy tracking for intensity smoothing
        self._energy_history: List[float] = []
        self._energy_window = 64  # frames

        # The one live section detector.
        self._detector = StreamingSectionDetector()

        # Callbacks
        self._on_section_change: Optional[Callable[[SongSection, SongSection], None]] = None

    @property
    def current_section(self) -> SongSection:
        return self._current_section

    @property
    def section_config(self) -> SectionConfig:
        return self._section_configs.get(self._current_section,
                                          DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN])

    def set_bpm(self, bpm: float):
        """Update BPM for timing calculations."""
        self._bpm = max(30.0, min(300.0, bpm))

    def set_section_config(self, section: SongSection, config: SectionConfig):
        """Override configuration for a section."""
        self._section_configs[section] = config

    def set_on_section_change(self, callback: Callable[[SongSection, SongSection], None]):
        """Set callback for section changes."""
        self._on_section_change = callback

    def set_crossfade_duration(self, bars: float):
        """Set crossfade duration in bars."""
        self._crossfade_duration_bars = max(0.0, bars)

    def set_anticipation(self, bars: float):
        """Set anticipation timing in bars."""
        self._anticipation_bars = max(0.0, bars)

    def _bars_to_seconds(self, bars: float) -> float:
        """Convert bars to seconds at current BPM."""
        beats_per_bar = 4
        return (bars * beats_per_bar * 60.0) / self._bpm

    def trigger_section(self, section: SongSection, immediate: bool = False):
        """
        Trigger a section change.

        Args:
            section: New section
            immediate: Skip crossfade if True
        """
        if section == self._current_section:
            return

        if immediate:
            self._execute_section_change(section)
        else:
            # Start crossfade transition
            crossfade_seconds = self._bars_to_seconds(self._crossfade_duration_bars)
            self._transition = SectionTransition(
                from_section=self._current_section,
                to_section=section,
                start_time=time.time(),
                duration=max(0.01, crossfade_seconds),
            )

    def schedule_section(self, section: SongSection, bars_ahead: float = None):
        """
        Schedule a section change with anticipation timing.

        Args:
            section: Target section
            bars_ahead: Bars ahead to trigger (uses default anticipation if None)
        """
        if bars_ahead is None:
            bars_ahead = self._anticipation_bars
        delay_seconds = self._bars_to_seconds(bars_ahead)
        self._pending_section = section
        self._pending_section_time = time.time() + delay_seconds

    def trigger_buildup(self, duration_beats: float = 8.0):
        """
        Start a build-up ramp that progressively increases intensity.

        Args:
            duration_beats: Build-up duration in beats
        """
        self._buildup_start_time = time.time()
        self._buildup_duration = duration_beats
        self._buildup_progress = 0.0
        self.trigger_section(SongSection.BUILDUP)

    def trigger_beat(self, beat_number: int):
        """Handle beat event."""
        self._beat_count = beat_number
        if beat_number % 4 == 0:
            self._bars_in_section += 1

    def _execute_section_change(self, section: SongSection):
        """Execute an immediate section change."""
        old_section = self._current_section
        self._previous_section = old_section
        self._current_section = section
        self._section_start_time = time.time()
        self._bars_in_section = 0
        self._transition = None

        if self._on_section_change:
            self._on_section_change(old_section, section)

    def update(self, delta_time: float, energy: float = 0.5, is_beat: bool = False):
        """
        Update section manager state.

        Args:
            delta_time: Time since last update
            energy: Current audio energy (0-1)
            is_beat: Whether a beat occurred this frame
        """
        current_time = time.time()

        # Track energy history
        self._energy_history.append(energy)
        if len(self._energy_history) > self._energy_window:
            self._energy_history = self._energy_history[-self._energy_window:]

        # Check pending scheduled section
        if (self._pending_section is not None and
                self._pending_section_time is not None and
                current_time >= self._pending_section_time):
            self.trigger_section(self._pending_section)
            self._pending_section = None
            self._pending_section_time = None

        # Update transition
        if self._transition is not None:
            elapsed = current_time - self._transition.start_time
            self._transition.progress = min(1.0, elapsed / self._transition.duration)
            if self._transition.is_complete:
                self._execute_section_change(self._transition.to_section)

        # Update build-up ramp
        if self._buildup_start_time is not None:
            beat_duration = 60.0 / self._bpm
            elapsed_beats = (current_time - self._buildup_start_time) / beat_duration
            self._buildup_progress = min(1.0, elapsed_beats / self._buildup_duration)
            if self._buildup_progress >= 1.0:
                self._buildup_start_time = None

        # Calculate target intensity
        self._target_intensity = self._calculate_target_intensity(energy, is_beat)

        # Smooth intensity
        blend = 1.0 - (1.0 - self._intensity_smoothing) ** (delta_time * 60.0)
        self._current_intensity += (self._target_intensity - self._current_intensity) * blend

    def _calculate_target_intensity(self, energy: float, is_beat: bool) -> float:
        """Calculate target intensity based on section and audio."""
        config = self.section_config
        min_i, max_i = config.intensity_range

        # Audio-reactive base within section range — energy drives the full span
        base = min_i + (max_i - min_i) * energy
        intensity = base

        # Beat bump
        if is_beat:
            beat_bump = config.beat_reactivity * 0.16
            intensity += beat_bump

        # Build-up ramp override
        if self._buildup_start_time is not None:
            # Progressive ramp from current min to max
            buildup_intensity = min_i + self._buildup_progress * (max_i - min_i)
            # Use quadratic ramp for more dramatic build
            ramp = self._buildup_progress ** 1.5
            buildup_intensity = min_i + ramp * (max_i - min_i)
            intensity = max(intensity, buildup_intensity)

        # Apply transition blending
        if self._transition is not None and not self._transition.is_complete:
            from_config = self._section_configs.get(
                self._transition.from_section,
                DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN]
            )
            from_min, from_max = from_config.intensity_range
            from_intensity = from_min + (from_max - from_min) * 0.5 + energy * from_config.beat_reactivity * (from_max - from_min)
            intensity = from_intensity + (intensity - from_intensity) * self._transition.progress

        # Apply dimmer floor
        intensity = max(config.dimmer_floor, intensity)

        # Clamp
        return max(0.0, min(1.0, intensity))

    def get_intensity(self) -> float:
        """Get current smoothed intensity output."""
        return self._current_intensity

    def get_intensity_range(self) -> Tuple[float, float]:
        """Get current section's intensity range."""
        return self.section_config.intensity_range

    def get_movement_energy(self) -> float:
        """Get movement energy multiplier for current section."""
        config = self.section_config

        # Apply transition blending
        if self._transition is not None and not self._transition.is_complete:
            from_config = self._section_configs.get(
                self._transition.from_section,
                DEFAULT_SECTION_CONFIGS[SongSection.UNKNOWN]
            )
            return (from_config.movement_energy +
                    (config.movement_energy - from_config.movement_energy) *
                    self._transition.progress)

        return config.movement_energy

    def get_color_saturation(self) -> float:
        """Get color saturation preference for current section."""
        return self.section_config.color_saturation

    def is_strobe_allowed(self) -> bool:
        """Check if strobe is allowed in current section."""
        return self.section_config.strobe_allowed

    def get_beat_reactivity(self) -> float:
        """Get beat reactivity for current section."""
        return self.section_config.beat_reactivity

    def get_buildup_progress(self) -> float:
        """Get current build-up progress (0-1), 0 if not in build-up."""
        if self._buildup_start_time is None:
            return 0.0
        return self._buildup_progress

    # Names the renderer switches on, mapped to the manager's richer enum.
    _LIVE_SECTION_ENUM = {
        "breakdown": SongSection.BREAKDOWN,
        "verse": SongSection.VERSE,
        "buildup": SongSection.BUILDUP,
        "chorus": SongSection.CHORUS,
        "drop": SongSection.DROP,
    }

    def update_section_from_audio(
        self,
        delta_time: Optional[float] = None,
        *,
        energy: float = 0.0,
        bass: float = 0.0,
        spectral_flux: float = 0.0,
        is_beat: bool = False,
        beat_number: int = 0,
        bpm: Optional[float] = None,
        is_downbeat_event: Optional[bool] = None,
        programme_level: Optional[float] = None,
        now: Optional[float] = None,
    ) -> str:
        """Run the live section detector for one frame and return its section.

        This is the entry point the renderer calls every frame. The returned
        name is always one of LIVE_SECTION_NAMES, and the manager's own section
        state is committed here so both stay in step.

        `now` is the caller's clock. Passing it keeps the detector's timers on
        the same timeline as its filters, which advance on `delta_time`; leaving
        it out falls back to the wall clock and is only correct for a caller
        stepping in real time.
        """
        decision = self._detector.update(
            delta_time,
            energy=energy,
            bass=bass,
            spectral_flux=spectral_flux,
            is_beat=is_beat,
            beat_number=beat_number,
            bpm=self._bpm if bpm is None else bpm,
            is_downbeat_event=is_downbeat_event,
            programme_level=programme_level,
            now=now,
        )
        if decision.changed:
            target = self._LIVE_SECTION_ENUM.get(decision.section)
            if target is not None and target != self._current_section:
                self._execute_section_change(target)
        return decision.section

    def detect_section_from_energy(
        self,
        energy: float,
        bass: float,
        spectral_flux: float,
        is_beat: bool = False,
        beat_number: int = 0,
        bars_elapsed: Optional[int] = None,
        is_downbeat_event: Optional[bool] = None,
        programme_level: Optional[float] = None,
        now: Optional[float] = None,
    ) -> Optional[SongSection]:
        """Adapter kept for the non-rebuild render path.

        Delegates to the same detector as `update_section_from_audio` and
        returns a section only on the frame it actually changes, which is the
        `None means no change` contract this call site already expects.
        """
        name = self.update_section_from_audio(
            None,
            energy=energy,
            bass=bass,
            spectral_flux=spectral_flux,
            is_beat=is_beat,
            beat_number=beat_number,
            is_downbeat_event=is_downbeat_event,
            programme_level=programme_level,
            now=now,
        )
        if not self._detector.decision.changed:
            return None
        return self._LIVE_SECTION_ENUM.get(name)

    def get_detection_debug(self) -> Dict[str, float | str | bool]:
        """Get latest streaming structure-detector debug state."""
        return self._detector.debug()
