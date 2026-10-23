"""
Effects: Tempo Zero, Shared Presets and the Last Line of Defence
================================================================

A tempo of 0 divided by zero in the decision engine's cooldowns and dropped
frames. A zero-length buildup divided by zero on every frame for ever. The
layers were handed the module's preset objects and rewrote them in place, so
after a few minutes "circle_slow" no longer moved. NaN reached the render step
as full on. And the clean-stage safety macro always raised.
"""

import copy
import math

import pytest

from app.services.effects import effects_engine as fx
from app.services.effects.decision_engine import CooldownTimer
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.fixture_groups import _level, _to_byte
from app.services.effects.movement_patterns import MOVEMENT_PRESETS, MovementEngine, MovementParams
from app.services.effects.strobe_controller import DropStrobeSequence, StrobeController


@pytest.mark.parametrize("bpm", [0, -10, float("nan"), float("inf"), None, "fast"])
def test_a_bad_tempo_does_not_drop_frames(bpm):
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    engine.update_audio(energy=0.5, bass=0.5, bpm=120.0)
    engine.update(1 / 60)
    engine.update_audio(energy=0.8, bass=0.9, is_beat=True, bpm=bpm)
    for _ in range(120):
        engine.update(1 / 60)
    assert engine.audio_state.bpm == 120.0


@pytest.mark.parametrize("bpm", [0, -1, float("nan")])
def test_cooldowns_survive_a_bad_tempo(bpm):
    timers = CooldownTimer()
    timers.set_cooldown("strobe", 4, bpm)
    assert math.isfinite(timers.timers["strobe"])


@pytest.mark.parametrize("duration", [0, -1, float("nan")])
def test_a_zero_length_buildup_ends(duration):
    controller = StrobeController()
    sequence = DropStrobeSequence(controller)
    sequence.trigger_buildup(duration)
    for _ in range(120):
        controller.time += 1 / 60
        sequence.update()
    assert sequence.phase != "buildup"
    assert controller.params.frequency >= 0


def test_running_the_show_leaves_the_presets_as_written():
    before = {
        "movement": copy.deepcopy(fx.MOVEMENT_PRESETS),
        "dimmer": copy.deepcopy(fx.DIMMER_PRESETS),
        "strobe": copy.deepcopy(fx.STROBE_PRESETS),
    }
    engine = EffectsEngine(EffectsConfig(auto_mode=True, strobe_enabled=True))
    for name in before["movement"]:
        engine._take_preset(engine.movement, "movement", fx.MOVEMENT_PRESETS, name)
        engine.movement.params.bpm = 128
        engine.movement.params.base_look = None
    for name in before["strobe"]:
        engine._take_preset(engine.strobe, "strobe", fx.STROBE_PRESETS, name)
        engine.strobe.stop()
    for frame in range(600):
        engine.update_audio(energy=0.9, bass=0.9, is_beat=frame % 30 == 0,
                            beat_number=frame // 30, bpm=128)
        engine.update(1 / 60)

    assert fx.MOVEMENT_PRESETS == before["movement"]
    assert fx.DIMMER_PRESETS == before["dimmer"]
    assert fx.STROBE_PRESETS == before["strobe"]


def test_a_held_preset_keeps_its_own_state_between_frames():
    engine = EffectsEngine()
    name = next(iter(fx.STROBE_PRESETS))
    engine._take_preset(engine.strobe, "strobe", fx.STROBE_PRESETS, name)
    held = engine.strobe.params
    engine._take_preset(engine.strobe, "strobe", fx.STROBE_PRESETS, name)
    assert engine.strobe.params is held


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_number_never_renders_as_full_on(value):
    assert _level(value) == 0.0
    assert _to_byte(value) == 0


def test_beat_divisor_counts_cycles_per_beat():
    movement = MovementEngine()
    movement.params = MovementParams(bpm=120, beat_divisor=0.25)  # one sweep per bar
    pan_hz, _ = movement._get_effective_speed()
    assert pan_hz == pytest.approx(0.5)
    assert MOVEMENT_PRESETS  # the presets this describes are still there


def test_clean_stage_macro_completes():
    engine = EffectsEngine()
    engine.clean_stage()
    assert engine.config.strobe_enabled is False
    assert engine._rebuild_color_hold_until > engine.time


def run_autopilot(engine, seconds):
    for frame in range(int(seconds * 60)):
        engine.update_audio(energy=0.4, bass=0.4, is_beat=frame % 30 == 0,
                            beat_number=frame // 30, bpm=120)
        engine.update(1 / 60)


def test_drop_button_reaches_the_autopilot():
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    run_autopilot(engine, 1)
    engine.trigger_drop_strobe()
    run_autopilot(engine, 1)
    assert engine._rebuild_section == "drop"

    run_autopilot(engine, EffectsEngine.OPERATOR_DROP_HOLD_S)
    assert engine._operator_section is None  # handed back to the detector


def test_buildup_button_builds_then_drops_on_the_autopilot():
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    run_autopilot(engine, 1)
    engine.trigger_buildup(2.0)
    run_autopilot(engine, 1)
    assert engine._rebuild_section == "buildup"
    run_autopilot(engine, 1.5)
    assert engine._rebuild_section == "drop"


def test_clean_stage_cancels_an_operator_drop():
    engine = EffectsEngine(EffectsConfig(auto_mode=True))
    engine.trigger_drop_strobe()
    engine.clean_stage()
    run_autopilot(engine, 0.5)
    assert engine._rebuild_section != "drop"
