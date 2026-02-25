"""Scene state machine for beam-pattern choreography."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from .beam_pattern_library import BeamPatternName, allowed_transitions


class ScenePhase(Enum):
    ENTER = "enter"
    HOLD = "hold"
    EXIT = "exit"


@dataclass(frozen=True)
class SceneTiming:
    """Timing envelope for beam scenes."""

    enter_duration_s: float
    hold_duration_s: float
    exit_duration_s: float
    cooldown_s: float


@dataclass
class SceneOutput:
    """State machine output consumed by pattern library integration."""

    active_pattern: BeamPatternName
    phase: ScenePhase
    phase_progress: float
    amplitude_scale: float


DEFAULT_SCENE_TIMINGS: Dict[BeamPatternName, SceneTiming] = {
    BeamPatternName.FAN: SceneTiming(enter_duration_s=0.75, hold_duration_s=8.0, exit_duration_s=0.5, cooldown_s=2.0),
    BeamPatternName.CROSSING_SWEEPS: SceneTiming(enter_duration_s=0.6, hold_duration_s=6.0, exit_duration_s=0.5, cooldown_s=2.5),
    BeamPatternName.MIRRORED_PAIRS: SceneTiming(enter_duration_s=0.65, hold_duration_s=7.0, exit_duration_s=0.55, cooldown_s=2.0),
    BeamPatternName.CIRCLES: SceneTiming(enter_duration_s=0.8, hold_duration_s=10.0, exit_duration_s=0.75, cooldown_s=3.0),
    BeamPatternName.AUDIENCE_SWEEP: SceneTiming(enter_duration_s=0.4, hold_duration_s=5.0, exit_duration_s=0.4, cooldown_s=3.0),
    BeamPatternName.CENTER_FOCUS_HOLD: SceneTiming(enter_duration_s=0.5, hold_duration_s=12.0, exit_duration_s=0.5, cooldown_s=1.5),
}


class BeamSceneStateMachine:
    """Controls enter/hold/exit progression and gated pattern transitions."""

    def __init__(self, initial_pattern: BeamPatternName = BeamPatternName.CENTER_FOCUS_HOLD):
        self._transition_map = allowed_transitions()
        self._timings = dict(DEFAULT_SCENE_TIMINGS)

        self._current_pattern = initial_pattern
        self._target_pattern = initial_pattern
        self._phase = ScenePhase.ENTER
        self._phase_elapsed = 0.0
        self._cooldowns: Dict[BeamPatternName, float] = {}

    @property
    def current_pattern(self) -> BeamPatternName:
        return self._current_pattern

    def request_transition(self, target_pattern: BeamPatternName, force: bool = False) -> bool:
        """Try to switch to a new target pattern using transition/cooldown constraints."""
        if target_pattern == self._target_pattern:
            return True

        if not force:
            if target_pattern in self._cooldowns and self._cooldowns[target_pattern] > 0:
                return False

            allowed_next = self._transition_map.get(self._current_pattern, set())
            if target_pattern not in allowed_next:
                return False

        self._target_pattern = target_pattern
        if target_pattern != self._current_pattern:
            self._phase = ScenePhase.EXIT
            self._phase_elapsed = 0.0
        return True

    def update(self, delta_time: float) -> SceneOutput:
        """Advance scene timing and return active output envelope."""
        dt = max(0.0, float(delta_time))

        for pattern in list(self._cooldowns.keys()):
            self._cooldowns[pattern] = max(0.0, self._cooldowns[pattern] - dt)
            if self._cooldowns[pattern] <= 0.0:
                del self._cooldowns[pattern]

        timing = self._timings[self._current_pattern]
        self._phase_elapsed += dt

        if self._phase == ScenePhase.ENTER:
            if self._phase_elapsed >= timing.enter_duration_s:
                self._phase = ScenePhase.HOLD
                self._phase_elapsed = 0.0

        elif self._phase == ScenePhase.HOLD:
            should_advance = self._current_pattern != self._target_pattern
            should_advance = should_advance or self._phase_elapsed >= timing.hold_duration_s
            if should_advance:
                self._phase = ScenePhase.EXIT
                self._phase_elapsed = 0.0

        elif self._phase == ScenePhase.EXIT:
            if self._phase_elapsed >= timing.exit_duration_s:
                self._cooldowns[self._current_pattern] = timing.cooldown_s
                self._current_pattern = self._target_pattern
                self._phase = ScenePhase.ENTER
                self._phase_elapsed = 0.0
                timing = self._timings[self._current_pattern]

        return SceneOutput(
            active_pattern=self._current_pattern,
            phase=self._phase,
            phase_progress=self._phase_progress(timing),
            amplitude_scale=self._phase_amplitude_scale(timing),
        )

    def _phase_progress(self, timing: SceneTiming) -> float:
        if self._phase == ScenePhase.ENTER:
            duration = max(0.01, timing.enter_duration_s)
        elif self._phase == ScenePhase.EXIT:
            duration = max(0.01, timing.exit_duration_s)
        else:
            duration = max(0.01, timing.hold_duration_s)
        return max(0.0, min(1.0, self._phase_elapsed / duration))

    def _phase_amplitude_scale(self, timing: SceneTiming) -> float:
        progress = self._phase_progress(timing)
        if self._phase == ScenePhase.ENTER:
            return 0.35 + progress * 0.65
        if self._phase == ScenePhase.EXIT:
            return 1.0 - progress * 0.55
        return 1.0
